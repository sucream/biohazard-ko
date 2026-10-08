// Biohazard (1996, Steam "4249100" release) Korean patch installer.
//
// Usage:
//
//	bh1_kor_patch.exe [game folder]            install
//	bh1_kor_patch.exe -uninstall [game folder] restore the original files
//
// Without a folder argument the patcher looks in its own folder and in the
// Steam library folders. Only XOR differences against the user's original
// files are stored in this program, so it contains no game data.
package main

import (
	"bufio"
	"bytes"
	"compress/zlib"
	"crypto/md5"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"golang.org/x/sys/windows/registry"
)

//go:embed payload
var payload embed.FS

type fileEntry struct {
	Path     string `json:"path"`
	Mode     string `json:"mode"`
	Data     string `json:"data"`
	OrigMD5  string `json:"orig_md5"`
	OrigSize int    `json:"orig_size"`
	NewMD5   string `json:"new_md5"`
	NewSize  int    `json:"new_size"`
}

type manifest struct {
	Name    string      `json:"name"`
	Version string      `json:"version"`
	ExeMD5  string      `json:"exe_md5"`
	Files   []fileEntry `json:"files"`
}

const backupDir = "japanese/kopatch_backup"

func md5hex(b []byte) string {
	s := md5.Sum(b)
	return hex.EncodeToString(s[:])
}

func readPayload(name string) ([]byte, error) {
	raw, err := payload.ReadFile("payload/" + name)
	if err != nil {
		return nil, err
	}
	r, err := zlib.NewReader(bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	return io.ReadAll(r)
}

func isGameDir(dir string) bool {
	_, err := os.Stat(filepath.Join(dir, "japanese", "Biohazard.exe"))
	return err == nil
}

// steamLibraries returns Steam library folders listed in libraryfolders.vdf.
func steamLibraries() []string {
	var out []string
	k, err := registry.OpenKey(registry.CURRENT_USER, `Software\Valve\Steam`, registry.QUERY_VALUE)
	if err != nil {
		return out
	}
	defer k.Close()
	steam, _, err := k.GetStringValue("SteamPath")
	if err != nil {
		return out
	}
	out = append(out, filepath.FromSlash(steam))
	vdf, err := os.ReadFile(filepath.Join(steam, "steamapps", "libraryfolders.vdf"))
	if err == nil {
		re := regexp.MustCompile(`"path"\s+"([^"]+)"`)
		for _, m := range re.FindAllStringSubmatch(string(vdf), -1) {
			out = append(out, strings.ReplaceAll(m[1], `\\`, `\`))
		}
	}
	return out
}

func findGame(arg string) (string, error) {
	if arg != "" {
		if isGameDir(arg) {
			return arg, nil
		}
		return "", fmt.Errorf("%s 에서 japanese\\Biohazard.exe 를 찾을 수 없습니다", arg)
	}
	exe, _ := os.Executable()
	cands := []string{filepath.Dir(exe), "."}
	for _, lib := range steamLibraries() {
		cands = append(cands, filepath.Join(lib, "steamapps", "common", "4249100_Biohazard"))
	}
	for _, c := range cands {
		if isGameDir(c) {
			return c, nil
		}
	}
	return "", errors.New("게임 폴더를 찾지 못했습니다. 패치 파일을 게임 폴더(4249100_Biohazard)에 넣고 실행하거나, 게임 폴더 경로를 인자로 주세요")
}

func install(game string, m manifest) error {
	exe, err := os.ReadFile(filepath.Join(game, "japanese", "Biohazard.exe"))
	if err != nil {
		return err
	}
	if md5hex(exe) != m.ExeMD5 {
		return errors.New("Biohazard.exe 버전이 다릅니다 (이 패치는 Steam판 BIOHAZARD 일본어 실행 파일 전용)")
	}
	// verify first, then write
	type job struct {
		e    fileEntry
		data []byte
	}
	var jobs []job
	for _, e := range m.Files {
		dst := filepath.Join(game, filepath.FromSlash(e.Path))
		diff, err := readPayload(e.Data)
		if err != nil {
			return err
		}
		if e.Mode == "new" {
			jobs = append(jobs, job{e, diff})
			continue
		}
		cur, err := os.ReadFile(dst)
		if err != nil {
			return err
		}
		if md5hex(cur) == e.NewMD5 {
			continue // already patched
		}
		orig := cur
		bak := filepath.Join(game, filepath.FromSlash(backupDir), filepath.FromSlash(e.Path))
		if md5hex(cur) != e.OrigMD5 {
			// patched by an older version of this patch? start from the backup
			if b, err := os.ReadFile(bak); err == nil && md5hex(b) == e.OrigMD5 {
				orig = b
			} else {
				return fmt.Errorf("%s 파일이 원본과 다릅니다", e.Path)
			}
		}
		out := make([]byte, e.NewSize)
		for i := range out {
			var o byte
			if i < len(orig) {
				o = orig[i]
			}
			out[i] = o ^ diff[i]
		}
		if md5hex(out) != e.NewMD5 {
			return fmt.Errorf("%s 패치 검증 실패", e.Path)
		}
		jobs = append(jobs, job{e, out})
		if _, err := os.Stat(bak); err != nil {
			if err := os.MkdirAll(filepath.Dir(bak), 0755); err != nil {
				return err
			}
			if err := os.WriteFile(bak, orig, 0644); err != nil {
				return err
			}
		}
	}
	for _, j := range jobs {
		dst := filepath.Join(game, filepath.FromSlash(j.e.Path))
		if err := os.WriteFile(dst, j.data, 0644); err != nil {
			return err
		}
		fmt.Println("  패치:", j.e.Path)
	}
	// files an older version changed that this version leaves alone
	inPatch := map[string]bool{}
	for _, e := range m.Files {
		inPatch[e.Path] = true
	}
	if err := restoreBackups(game, func(rel string) bool { return !inPatch[rel] }); err != nil {
		return err
	}
	setLauncherJapanese(game)
	return nil
}

// setLauncherJapanese selects the Japanese executable in the Steam launcher.
func setLauncherJapanese(game string) {
	ini := filepath.Join(game, "4249100_Launcher.ini")
	b, err := os.ReadFile(ini)
	if err != nil {
		return
	}
	re := regexp.MustCompile(`(?m)^LanguageSetting=.*$`)
	nb := re.ReplaceAll(b, []byte("LanguageSetting=japanese\r"))
	if !bytes.Equal(b, nb) {
		os.WriteFile(ini, nb, 0644)
		fmt.Println("  런처 언어를 japanese 로 설정했습니다")
	}
}

// restoreBackups copies backed-up originals selected by want back into the
// game folder and removes them from the backup.
func restoreBackups(game string, want func(rel string) bool) error {
	root := filepath.Join(game, filepath.FromSlash(backupDir))
	return filepath.Walk(root, func(p string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			return nil
		}
		r, _ := filepath.Rel(root, p)
		rel := filepath.ToSlash(r)
		if !want(rel) {
			return nil
		}
		b, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		if err := os.WriteFile(filepath.Join(game, r), b, 0644); err != nil {
			return err
		}
		os.Remove(p)
		fmt.Println("  복원:", rel)
		return nil
	})
}

func uninstall(game string, m manifest) error {
	for _, e := range m.Files {
		if e.Mode == "new" {
			os.Remove(filepath.Join(game, filepath.FromSlash(e.Path)))
			fmt.Println("  삭제:", e.Path)
		}
	}
	if err := restoreBackups(game, func(string) bool { return true }); err != nil {
		return err
	}
	os.RemoveAll(filepath.Join(game, filepath.FromSlash(backupDir)))
	return nil
}

func main() {
	fmt.Println("바이오하자드 (1996) 한글 패치")
	args := os.Args[1:]
	undo := false
	if len(args) > 0 && (args[0] == "-uninstall" || args[0] == "/uninstall") {
		undo = true
		args = args[1:]
	}
	dir := ""
	if len(args) > 0 {
		dir = args[0]
	}
	err := run(dir, undo)
	if err != nil {
		fmt.Println()
		fmt.Println("오류:", err)
	}
	fmt.Println()
	fmt.Print("엔터 키를 누르면 종료합니다...")
	bufio.NewReader(os.Stdin).ReadString('\n')
	if err != nil {
		os.Exit(1)
	}
}

func run(dir string, undo bool) error {
	var m manifest
	raw, err := payload.ReadFile("payload/manifest.json")
	if err != nil {
		return err
	}
	if err := json.Unmarshal(raw, &m); err != nil {
		return err
	}
	fmt.Printf("버전 %s\n\n", m.Version)
	game, err := findGame(dir)
	if err != nil {
		return err
	}
	fmt.Println("게임 폴더:", game)
	if undo {
		if err := uninstall(game, m); err != nil {
			return err
		}
		fmt.Println("원래 상태로 복원했습니다.")
		return nil
	}
	if err := install(game, m); err != nil {
		return err
	}
	fmt.Println()
	fmt.Println("설치 완료! Steam 런처에서 언어를 'Japanese'로 두고 게임을 시작하세요.")
	fmt.Println("제거하려면: bh1_kor_patch.exe -uninstall")
	return nil
}
