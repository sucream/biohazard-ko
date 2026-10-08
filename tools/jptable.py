"""Japanese Biohazard (PC) font cell -> character table, for decoding original text."""
P0_ASCII = ('　■▶①②③④△○×□▼0123456789：、。”！？⁉ABCDEFGHIJKLMNOPQRSTUVWXYZ［／］’ー・'
            'abcdefghijklmnopqrstuvwxyz')
HIRA = ('あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん'
        'がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽぁぃぅぇぉゃゅょっ')
KATA = ('アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン'
        'ガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポァィゥェォャュョッヴ')
P0_TAIL = ('ーー「」', ['S.', 'T.', 'A.', 'R.'], '（）『』〃〃．×上右下左悪安暗穴員遺育意違一炎役押俺奥応回拡兜火')
P1 = ('壊楽何外確感関開間館方会怪家完救急機'
      '御寄究記器起況机気危許凶強供給空君具'
      '決血剣研係見形険撃元経験構後号古行合'
      '攻刻光今口効言向降酸剤査残最殺作縮小'
      '進信室宿舎盾書飼写真取指子射除紙状純'
      '仕手私食時出事銃術丈少死使実失持助身'
      '心自重消蛇緒守思者図水前清青赤制生成'
      '石先整性洗全戸跡接切染草捜造装像槽存'
      '続族騒大退弾単誰棚台男他待体脱地調置'
      '中知通転定電庭動当踏逃毒倒得特日人入'
      '認任燃年配白敗反破発美備必物譜不風夫'
      '分部普聞並別変放宝本保報味無面迷滅目'
      '戻薬屋奴用鎧要熔様来頼落力硫料理流立'
      '裏令連練路話…ゝ々溶液絡四六角抜所同'
      '久階計月告索女習準充社喋傷受冗製属巣'
      '多短対断談治仲丸点堂度内念判品怖墓油'
      '療送枯願玉遇固根好天紫星神情遭滝答緑'
      '息＝十西東〓未誌証番有化学長警資植絵')
P3N_TAIL = ('委運映横誘解額覚緊級近極泣議責愚厳欠'
            '勇径広乱故公獄際常〓場〓焼趣弱姿主貴'
            '世測第態賞団超伝隷記都届能爆半非兵歩'
            '法防〓命野招未誌証番有化学長警資植絵')


def page0():
    t = list(P0_ASCII) + list(HIRA) + list(KATA)
    t += list(P0_TAIL[0]) + P0_TAIL[1] + list(P0_TAIL[2])
    assert len(t) == 288, len(t)
    return t


def page1(stage5=False):
    p = list(P1)
    assert len(p) == 324, len(p)
    if stage5:
        p[252:] = list(P3N_TAIL)
    return p


def decode(m, stage5=False, ctrl=True):
    """Decode a message byte string into readable text with control tags."""
    p0, p1 = page0(), page1(stage5)
    out = []
    i = 0
    while i < len(m):
        b = m[i]
        if b == 0xF8:
            out.append(p0[234 + m[i + 1]]); i += 2
        elif b == 0xF9:
            out.append(p1[m[i + 1]]); i += 2
        elif b == 0xFA:
            out.append(p1[252 + m[i + 1]]); i += 2
        elif b >= 0xFB:
            out.append('{%02X%02X}' % (b, m[i + 1])); i += 2
        elif ctrl and b == 1:
            out.append('<END:%d>' % m[i + 1] if i + 1 < len(m) else '<END>'); i += 2
        elif ctrl and b == 2:
            out.append('\n'); i += 1
        elif ctrl and b in (3, 4, 5, 6, 8):
            out.append('<%s:%d>' % ({3: 'PAGE', 4: 'C4', 5: 'COL', 6: 'ITEM', 8: 'YESNO'}[b], m[i + 1])); i += 2
        elif ctrl and b == 7:
            out.append('<RET>'); i += 1
        else:
            out.append(p0[b]); i += 1
    return ''.join(out)
