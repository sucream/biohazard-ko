// Biohazard (1996, Steam "4249100" release) Korean patch installer.
//
// Usage:
//
//	bh1_kor_patch.exe [game folder]            install
//	bh1_kor_patch.exe -uninstall [game folder] remove the Korean version
//
// The Korean version is installed into its own folder, korean\, next to
// japanese\ (which stays untouched), and the Steam launcher gets a "korean"
// entry in its language list. Unchanged game data is hard-linked from
// japanese\ (copied if the drive does not support links). Movies with
// burned-in Japanese subtitles are replaced by links to the subtitle-free
// North American ones from english\ (the DLL draws Korean subtitles).
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
	Dest     string `json:"dest"`
	Mode     string `json:"mode"`
	Src      string `json:"src"`
	Backup   bool   `json:"backup"`
	Data     string `json:"data"`
	OrigMD5  string `json:"orig_md5"`
	OrigSize int    `json:"orig_size"`
	NewMD5   string `json:"new_md5"`
	NewSize  int    `json:"new_size"`
}

type manifest struct {
	Name    string      `json:"name"`
	Version string      `json:"version"`
	Source  string      `json:"source"`
	Target  string      `json:"target"`
	ExeMD5  string      `json:"exe_md5"`
	Files   []fileEntry `json:"files"`
}

const (
	backupDir       = "kopatch_backup"          // originals of files patched in place
	legacyBackupDir = "japanese/kopatch_backup" // 1.0/1.1 patched japanese\ in place
	launcherIni     = "4249100_Launcher.ini"
)

func md5hex(b []byte) string {
	s := md5.Sum(b)
	return hex.EncodeToString(s[:])
}

// fileMD5 returns the MD5 of a file, or "" if it cannot be read.
func fileMD5(p string) string {
	f, err := os.Open(p)
	if err != nil {
		return ""
	}
	defer f.Close()
	h := md5.New()
	if _, err := io.Copy(h, f); err != nil {
		return ""
	}
	return hex.EncodeToString(h.Sum(nil))
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

func exists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

func isGameDir(dir string) bool {
	return exists(filepath.Join(dir, "japanese", "Biohazard.exe"))
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

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	return out.Close()
}

// restoreBackups copies every file under dir (paths relative to the game
// folder) back into place and deletes dir.
func restoreBackups(game, dir string) error {
	root := filepath.Join(game, filepath.FromSlash(dir))
	if !exists(root) {
		return nil
	}
	err := filepath.Walk(root, func(p string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			return err
		}
		rel, _ := filepath.Rel(root, p)
		if err := copyFile(p, filepath.Join(game, rel)); err != nil {
			return err
		}
		fmt.Println("  복원:", filepath.ToSlash(rel))
		return nil
	})
	if err != nil {
		return err
	}
	return os.RemoveAll(root)
}

// migrateLegacy undoes a 1.0/1.1 installation, which patched japanese\ in place.
func migrateLegacy(game string) error {
	if !exists(filepath.Join(game, filepath.FromSlash(legacyBackupDir))) {
		return nil
	}
	fmt.Println("이전 버전(japanese 폴더에 덮어쓴 설치)을 원래대로 되돌립니다")
	if err := restoreBackups(game, legacyBackupDir); err != nil {
		return err
	}
	os.Remove(filepath.Join(game, "japanese", "version.dll"))
	os.Remove(filepath.Join(game, "japanese", "kopatch.log"))
	return nil
}

// mirror fills target\ from source\: game data (JPN\) is hard-linked, the
// small executables and settings are copied. Saves are copied once.
func mirror(game string, m manifest, patched map[string]bool) error {
	src := filepath.Join(game, m.Source)
	dst := filepath.Join(game, m.Target)
	linked, copied := 0, 0
	err := filepath.Walk(src, func(p string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(src, p)
		top := strings.ToUpper(strings.SplitN(filepath.ToSlash(rel), "/", 2)[0])
		if info.IsDir() {
			if top == "SAVE" || top == "KOPATCH_BACKUP" {
				return filepath.SkipDir
			}
			return os.MkdirAll(filepath.Join(dst, rel), 0755)
		}
		name := strings.ToLower(info.Name())
		if name == "version.dll" || name == "kopatch.log" {
			return nil
		}
		out := filepath.Join(dst, rel)
		if patched[strings.ToLower(filepath.ToSlash(filepath.Join(m.Target, rel)))] {
			return nil
		}
		if top == "JPN" {
			os.Remove(out)
			if os.Link(p, out) == nil {
				linked++
				return nil
			}
		} else if strings.HasSuffix(name, ".ini") && exists(out) {
			return nil // keep the Korean version's own settings
		}
		copied++
		return copyFile(p, out)
	})
	if err != nil {
		return err
	}
	fmt.Printf("  %s 폴더 구성: 링크 %d개, 복사 %d개\n", m.Target, linked, copied)

	saveDst := filepath.Join(dst, "SAVE")
	if !exists(saveDst) {
		if err := os.MkdirAll(saveDst, 0755); err != nil {
			return err
		}
		saves, _ := filepath.Glob(filepath.Join(src, "SAVE", "*"))
		for _, s := range saves {
			if err := copyFile(s, filepath.Join(saveDst, filepath.Base(s))); err != nil {
				return err
			}
		}
		if len(saves) > 0 {
			fmt.Println("  일본어판 세이브를 korean\\SAVE 로 복사했습니다")
		}
	}
	return nil
}

func install(game string, m manifest) error {
	exe, err := os.ReadFile(filepath.Join(game, m.Source, "Biohazard.exe"))
	if err != nil {
		return err
	}
	if md5hex(exe) != m.ExeMD5 {
		return errors.New("Biohazard.exe 버전이 다릅니다 (이 패치는 Steam판 BIOHAZARD 일본어 실행 파일 전용)")
	}
	if err := migrateLegacy(game); err != nil {
		return err
	}

	// verify and prepare everything first, then write
	type job struct {
		e    fileEntry
		data []byte
		orig []byte // original to back up (in-place files)
	}
	var jobs []job
	var links []fileEntry
	patched := map[string]bool{}
	for _, e := range m.Files {
		if e.Mode == "link" {
			// subtitle-free North American movie in place of a Japanese one
			if fileMD5(filepath.Join(game, filepath.FromSlash(e.Src))) == e.OrigMD5 {
				patched[strings.ToLower(e.Dest)] = true
				links = append(links, e)
			} else {
				fmt.Printf("  %s 이(가) 없거나 원본과 달라 일본어판 영상을 씁니다 (일본어 자막을 가리고 한글 자막 표시)\n", e.Src)
			}
			continue
		}
		patched[strings.ToLower(e.Dest)] = true
		diff, err := readPayload(e.Data)
		if err != nil {
			return err
		}
		if e.Mode == "new" {
			jobs = append(jobs, job{e, diff, nil})
			continue
		}
		var orig []byte
		bak := filepath.Join(game, backupDir, filepath.FromSlash(e.Src))
		if e.Backup {
			cur, err := os.ReadFile(filepath.Join(game, filepath.FromSlash(e.Dest)))
			if err != nil {
				return err
			}
			switch {
			case md5hex(cur) == e.OrigMD5:
				orig = cur
			case exists(bak):
				// already patched (this or another version): start from the backup
				if orig, err = os.ReadFile(bak); err != nil {
					return err
				}
			default:
				orig = cur
			}
		} else if orig, err = os.ReadFile(filepath.Join(game, filepath.FromSlash(e.Src))); err != nil {
			return err
		}
		if md5hex(orig) != e.OrigMD5 {
			return fmt.Errorf("%s 파일이 원본과 다릅니다. Steam에서 '게임 파일 무결성 확인'을 한 뒤 다시 설치하세요", e.Src)
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
			return fmt.Errorf("%s 패치 검증 실패", e.Dest)
		}
		j := job{e, out, nil}
		if e.Backup && !exists(bak) {
			j.orig = orig
		}
		jobs = append(jobs, j)
	}

	if err := mirror(game, m, patched); err != nil {
		return err
	}
	for _, j := range jobs {
		if j.orig != nil {
			bak := filepath.Join(game, backupDir, filepath.FromSlash(j.e.Src))
			if err := os.MkdirAll(filepath.Dir(bak), 0755); err != nil {
				return err
			}
			if err := os.WriteFile(bak, j.orig, 0644); err != nil {
				return err
			}
		}
		dst := filepath.Join(game, filepath.FromSlash(j.e.Dest))
		if err := os.MkdirAll(filepath.Dir(dst), 0755); err != nil {
			return err
		}
		os.Remove(dst) // never write through a hard link
		if err := os.WriteFile(dst, j.data, 0644); err != nil {
			return err
		}
	}
	for _, e := range links {
		src := filepath.Join(game, filepath.FromSlash(e.Src))
		dst := filepath.Join(game, filepath.FromSlash(e.Dest))
		os.Remove(dst) // never write through a hard link
		if os.Link(src, dst) != nil {
			if err := copyFile(src, dst); err != nil {
				return err
			}
		}
	}
	fmt.Printf("  한글 파일 %d개 설치\n", len(jobs))
	if len(links) > 0 {
		fmt.Printf("  자막 없는 북미판 영상 %d개 연결\n", len(links))
	}
	setLauncherLanguage(game, "", m.Target)
	return nil
}

// setLauncherLanguage sets LanguageSetting in the launcher ini to lang (only
// if it currently is from, when from is not empty).
func setLauncherLanguage(game, from, lang string) {
	ini := filepath.Join(game, launcherIni)
	b, err := os.ReadFile(ini)
	if err != nil {
		return
	}
	re := regexp.MustCompile(`(?m)^LanguageSetting=([^\r\n]*)`)
	m := re.FindSubmatch(b)
	if m == nil || string(m[1]) == lang || (from != "" && string(m[1]) != from) {
		return
	}
	nb := re.ReplaceAll(b, []byte("LanguageSetting="+lang))
	if os.WriteFile(ini, nb, 0644) == nil {
		fmt.Println("  런처 언어를", lang, "(으)로 설정했습니다")
	}
}

func uninstall(game string, m manifest) error {
	if err := migrateLegacy(game); err != nil {
		return err
	}
	if err := restoreBackups(game, backupDir); err != nil {
		return err
	}
	// remove the Korean folder, keeping its saves
	dst := filepath.Join(game, m.Target)
	entries, _ := os.ReadDir(dst)
	for _, e := range entries {
		if strings.EqualFold(e.Name(), "SAVE") {
			continue
		}
		if err := os.RemoveAll(filepath.Join(dst, e.Name())); err != nil {
			return err
		}
	}
	if saves, _ := os.ReadDir(filepath.Join(dst, "SAVE")); len(saves) > 0 {
		fmt.Println("  한글판 세이브는 korean\\SAVE 에 남겨 두었습니다")
	} else {
		os.RemoveAll(dst)
	}
	fmt.Println("  삭제:", m.Target)
	setLauncherLanguage(game, m.Target, m.Source)
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
		fmt.Println("한글판을 제거했습니다. (일본어판 japanese 폴더는 원본 그대로입니다)")
		return nil
	}
	if err := install(game, m); err != nil {
		return err
	}
	fmt.Println()
	fmt.Println("설치 완료! Steam에서 게임을 시작하고 런처의 언어 목록에서 'korean'을 선택하세요.")
	fmt.Println("일본어판은 'japanese'를 선택하면 원래대로 실행됩니다.")
	fmt.Println("제거하려면: bh1_kor_patch.exe -uninstall")
	return nil
}
