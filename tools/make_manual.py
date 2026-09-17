# -*- coding: utf-8 -*-
r"""生成 KTRT 使用说明 PDF。

用法（reportlab 在 Codex 运行时 python 里）：
runtime_python tools/make_manual.py --version 0.2.0c --out "C:\桌面\KTRT使用说明_内测版.pdf" --test-key sk-xxx
runtime_python tools/make_manual.py --version 0.2.0c --out "C:\桌面\KTRT使用说明.pdf"
runtime_python tools/make_manual.py --version 0.2.0c --out frontend/static/docs/guide_usage.pdf

命名约定：**输出文件名不带版本号**，版本号只写在文档内容里（副标题与页脚）。
每次发版重新生成时把 --version 换成新版本即可，文件名保持不变。
带 --test-key 时插入测试 Key 提示框并标成内测发放版；不带则写“填自己的 Key”（随程序分发的公开版用这个）。
"""
import argparse
import os
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_DIR = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')


def register_fonts():
    pdfmetrics.registerFont(TTFont('KTRT', os.path.join(FONT_DIR, 'msyh.ttc'), subfontIndex=0))
    pdfmetrics.registerFont(TTFont('KTRT-Bold', os.path.join(FONT_DIR, 'msyhbd.ttc'), subfontIndex=0))
    pdfmetrics.registerFontFamily('KTRT', normal='KTRT', bold='KTRT-Bold',
                                  italic='KTRT', boldItalic='KTRT-Bold')


def build_styles():
    return dict(
        title=ParagraphStyle('t', fontName='KTRT-Bold', fontSize=22, leading=30,
                             textColor=colors.HexColor('#16305b'), spaceAfter=4),
        sub=ParagraphStyle('s', fontName='KTRT', fontSize=10.5, leading=15,
                           textColor=colors.HexColor('#6b7280'), spaceAfter=14),
        h=ParagraphStyle('h', fontName='KTRT-Bold', fontSize=14, leading=20,
                         textColor=colors.HexColor('#2b56d4'), spaceBefore=13, spaceAfter=6),
        body=ParagraphStyle('b', fontName='KTRT', fontSize=10.5, leading=17.5,
                            textColor=colors.HexColor('#1f2937'), spaceAfter=4),
        li=ParagraphStyle('li', fontName='KTRT', fontSize=10.5, leading=17.5,
                          textColor=colors.HexColor('#1f2937'), leftIndent=14, spaceAfter=3),
        tip=ParagraphStyle('tip', fontName='KTRT', fontSize=10, leading=16,
                           textColor=colors.HexColor('#7a3e00'), spaceAfter=4),
    )


def content(version, test_key, styles, width):
    def P(text, style='body'):
        return Paragraph(text, styles[style])

    story = []
    story.append(P('KTRT 使用说明', 'title'))
    story.append(P('溯源词斩 KTRT（KillTimeRecitationTool）v%s · %s · 开发者 HoweyYueng'
                   % (version, '内测试用版' if test_key else '正式版'), 'sub'))
    if test_key:
        story.append(P('<b>本册为内测发放版，内含测试专用 Key，请勿对外转发。</b>'
                       '正式版说明书（不含 Key）随程序与仓库一同发布。', 'tip'))
    story.append(P('KTRT 是一个本地优先的背单词程序：一页一个词，音标、词性释义、搭配、短语、同反义词、'
                   '同根词全摊开；另带 AI 造句、四选一闯关、风暴词卡、自定义查词、单词笔记本、'
                   '离线词典（ECDICT 77 万词条）与语音朗读。不开外网端口，词汇数据只存在你自己的电脑上。'))

    story.append(P('一、安装与启动', 'h'))
    story.append(P('1. 双击安装包 <b>KTRTSetup-lite-%s.exe</b>，安装器会让你选语言（简体中文 / 繁体中文 / 英语），一路下一步。' % version, 'li'))
    story.append(P('2. 装完自动创建桌面快捷方式。纯净版安装包<b>不含词库</b>，词库按第三节导入。', 'li'))
    story.append(P('3. 双击桌面「KTRT」启动：先出现预备窗口（准备词库、拉起本地服务），随后浏览器自动打开 http://127.0.0.1:8000 ，看到页面即可用。', 'li'))
    story.append(P('4. 程序在后台常驻，没有终端黑窗。关掉浏览器标签不影响使用，下次打开快捷方式会直接连上（同一时间只跑一个实例）。', 'li'))
    story.append(P('5. 想彻底退出：任务管理器里结束 pythonw.exe（源码版）或 KTRT.exe（安装版）进程即可；不结束也不影响电脑。', 'li'))

    story.append(P('二、接入 AI' + ('（测试 Key）' if test_key else '（填自己的 Key）'), 'h'))
    story.append(P('AI 用在三处：单词造句、风暴词卡生成、自定义查词的机翻与添加新词条。不填 Key 也能背词、查离线词典、'
                   '闯关、记笔记，只是这三处用不了。', 'body'))
    story.append(P('1. 打开左侧「设置」页。', 'li'))
    story.append(P('2. 「模型厂商」选 <b>DeepSeek</b>；Base URL 与模型名保持默认（https://api.deepseek.com 与 deepseek-chat）。', 'li'))
    story.append(P('3. 在「API Key」里填入：', 'li'))
    if test_key:
        key_style = ParagraphStyle('k', fontName='KTRT-Bold', fontSize=12, leading=18,
                                   textColor=colors.HexColor('#7a3e00'))
        key_table = Table([[Paragraph(test_key, key_style)]], colWidths=[width])
        key_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff3cd')),
            ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#f0c36d')),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ]))
        story.append(key_table)
        story.append(Spacer(1, 4))
        story.append(P('说明：这是<b>测试专用 Key</b>，仅用于体验与验收，多人同时使用可能限流。长期使用请换成自己的 Key'
                       '（DeepSeek / 豆包 / GPT / Gemini / Claude / 千问 / Grok 都能填，厂商、模型随时可换）。', 'tip'))
    else:
        story.append(P('你自己的 API Key（到所选厂商的开放平台申请，形如 sk-xxxx）。', 'tip'))
    story.append(P('4. 点「保存设置」，再点「测试 AI」，提示连接成功即完成。', 'li'))
    story.append(P('5. 之后想换厂商 / 换模型，回这一页改完再保存即可，学习记录不受影响。', 'li'))

    story.append(P('三、导入词库', 'h'))
    story.append(P('程序自带三本已整理好的词库，可直接下载：', 'body'))
    story.append(P('- GRE 必背（6519 词）· 雅思词汇真经（3608 词）· 考研英语词汇词根+联想记忆法（5905 词）', 'li'))
    story.append(P('下载与导入：打开「导入」页 →「词书资源」区点对应「下载」（或到仓库 wordbooks/ 目录下载）→ '
                   '回到上面「选择文件」挑这个 xlsx →「单词书名」可留空（默认取文件名）→「语言」选英语 → 点「导入」，'
                   '提示“导入成功：xxx，N 词”即完成。', 'li'))
    story.append(P('自己整理词书：把手上任何单词书（Excel、PDF、Word、图片、电子书都行）交给 AI，'
                   '点「导入」页的「复制自制词书提示词」，把提示词一并粘贴过去，让它按 11 列【】格式整理成 Excel，再按上面步骤导入。'
                   '提示词全文见 docs/词书整理提示词.md。', 'li'))
    story.append(P('导入页下方「已导入的单词书」可删除任意一本（默认书不可删）。重复导入同名书是按 List + 序号覆盖更新，不会越导越多。', 'li'))

    story.append(P('四、学词页', 'h'))
    story.append(P('- 顶部选<b>单词书</b>和 <b>List</b>，进度条显示已背 / 总数；键盘 ← / → 也能翻词。', 'li'))
    story.append(P('- 单词卡：单词加粗置顶，下面是音标、词性释义、<b>搭配与短语</b>（合并为一栏，本词优先 → 更短优先 → 字母序）、'
                   '同义词、反义词、同根词；每个字段旁的朗读键可以单独读那一行，主单词键也能随时点停。', 'li'))
    story.append(P('- <b>动词短语参考</b>：内置动词短语库 2217 条 / 3214 个义项（中文释义、例句中译、语域、学习价值）。'
                   '导入词书时按动词自动检索写入，卡片下方直接列出，可展开看全部义项；名词不参与检索。', 'li'))
    story.append(P('- 标记与进度：「背」计入进度并跳下一个；「熟悉 / 不熟悉 / 收藏」可组合点、再点取消；'
                   '小书签图标一键留标记，顶部下拉可直达；每本书各自记住上次学到哪。', 'li'))
    story.append(P('- <b>编辑词条</b>：音标右侧的铅笔图标，点开就在卡片里改这一条（单词、音标、词性释义、搭配、短语、'
                   '同义词、反义词、同根词），保存后同步本地数据库，并回写这本词书的 Excel 对应行；'
                   '原文件被移动 / 删除时自动写到 data/wordbooks 下的托管副本。发现音标或释义有误，直接改这里即可。', 'li'))
    story.append(P('- AI 造句：输入一句中文提示（如“他努力弥补过错”），点「生成造句」，会高亮目标词并配中文翻译，存进造句收藏；'
                   '每词最多 3 句，超了自动删最旧的。', 'li'))
    story.append(P('- 查词典：卡片下方「查词典」用内置 ECDICT 离线词典速查，断网也能用。', 'li'))
    story.append(P('- 单词笔记本：卡片右侧写 Markdown 笔记（行首 # / ## 变标题，Ctrl+B 加粗，选中右键高亮），'
                   '样式即见即所得，点「保存」生效。<b>笔记按词共用</b>：同一个词出现在几本词书里，笔记都是同一份；'
                   '导出时仍按词书分别导出。', 'li'))
    story.append(P('- 风暴：为当前词生成结构化词卡（见下一节）。', 'li'))

    story.append(P('五、查词与风暴词卡', 'h'))
    story.append(P('自定义查词典（学词页顶部按钮）：', 'body'))
    story.append(P('- 输入英文单词 / 短语 / 句子，或直接输中文（自动中↔英机翻），点「查询」。', 'li'))
    story.append(P('- 结果依次是：离线词典释义 → 机翻 → Datamuse 在线联想（同音近音、形似词，查询后自动加载，不用点按钮）。', 'li'))
    story.append(P('- 结果下方列出这个词<b>所在词书</b>，点词书芯片直接跳到那本书对应的 List 与序号位置。', 'li'))
    story.append(P('- 「+ 添加到外部单词收藏册」：单词按原形入库（大小写、复数等变形自动归一），'
                   '入库后和其他词书一样能背、能导出；如果是短语或句子，则只保留释义条目（类型 + 译文 + 使用场景 + 拆解）。', 'li'))
    story.append(P('- 「风暴词卡」按钮：这个词已经有词卡就原地预览，没有就跳到风暴页生成。', 'li'))
    story.append(P('风暴词卡页：输入单词点生成，AI 产出百科词源、使用场景、释义、词形变化、搭配、介词搭配、短语、'
                   '俚语习语、衍生词、同义词 / 近义词（含语义区别）、反义词、形似易混淆词；可单条或批量导出 Excel / Markdown。'
                   '词卡里的词书芯片同样可点，方便定位它在哪本书里。', 'body'))

    story.append(P('六、杀词（闯关）', 'h'))
    story.append(P('- 记词闯关：以 List 为最小单元，四选一匹配词性释义，每局乱序；答错自动标「不熟悉」并即时进错题本；记录每个 List 最高分。', 'li'))
    story.append(P('- 错题闯关：可多选 List 合并题池，答对可选移出错题本。', 'li'))
    story.append(P('- 答题中进入专注模式（只剩题目和退出键）；切页会清空本局进度，已进错题本的词保留。', 'li'))

    story.append(P('七、管理页', 'h'))
    story.append(P('- 搜索框按单词 / 音标即时过滤；下拉按 熟悉 / 不熟悉 / 收藏 / 已背 / 有造句 / 有笔记 筛选。', 'li'))
    story.append(P('- 列表按 单词书 → List 分组，可折叠；每行能删除该词的学习记录。', 'li'))
    story.append(P('- 导出：选范围（不熟悉 / 收藏 / 一并）+ 词书 + List，导成 Excel，每行是该词在词库里的完整一行，还能再导回来；'
                   '「导出笔记」把范围内笔记导成 Markdown。', 'li'))
    story.append(P('- 清空进度：按词书 + List 清空「已背」，收藏 / 熟悉 / 笔记不受影响；另可单独清空笔记。', 'li'))

    story.append(P('八、设置页', 'h'))
    story.append(P('1. 界面质感与配色：三种页面质感，每种质感各三套配色，侧栏三个颜色按钮随质感自动换名。', 'body'))
    theme_rows = [
        ['页面质感', '配色一', '配色二', '配色三'],
        ['简约（Apple / OpenAI 风）', '浅色', '深色', '石墨'],
        ['纸质（纸纹 + 衬线字体）', '米白纸', '牛皮纸', '靛蓝纸'],
        ['科幻（霓虹夜景 / 扫描线）', '霓虹', '酸黄', '矩阵'],
    ]
    tbl = Table([[Paragraph(c, ParagraphStyle('c', fontName='KTRT' if i else 'KTRT-Bold', fontSize=9.5,
                                              leading=14, textColor=colors.HexColor('#1f2937'))) for c in row]
                 for i, row in enumerate(theme_rows)],
                colWidths=[width * 0.34, width * 0.22, width * 0.22, width * 0.22])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef2ff')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 4))
    story.append(P('2. AI 配置：厂商 / Base URL / 模型名 / API Key，改完点「保存设置」，可点「测试 AI」验证。', 'li'))
    story.append(P('3. 朗读：<b>edge-tts</b>（联网，音质好）或<b>浏览器语音</b>（完全离线）；英语有美音 / 英音 × 男 / 女四选，'
                   '法语男 / 女声；语速、音调、音量都能调。朗读键连点会中断在途合成并停掉上一段，不会叠音。', 'li'))
    story.append(P('九、更新页', 'h'))
    story.append(P('- 「检查更新」读取 GitHub 上的最新发布：有热补丁就一键应用，不用重启，刷新页面即生效；'
                   '有新版本就下载安装包并静默安装，装完自动重开（会弹一次系统授权框，点“是”即可）。', 'li'))
    story.append(P('- 「启动时自动检查更新」默认打开：有新版或补丁会开程序时弹窗提示，可以选「稍后」或「本版本不再提醒」。', 'li'))
    story.append(P('- 源码版不提供一键安装：检查到新版本会给出 Release 页面链接，自己 git pull 或下载即可。', 'li'))
    story.append(P('- 补丁包与安装包都来自本项目的 GitHub Release；热补丁不需要管理员权限，安装包更新也不会动 data 目录里的学习数据。', 'li'))

    story.append(P('十、数据、备份与隐私', 'h'))
    story.append(P('- 数据目录：安装版在 <b>%APPDATA%\\KTRT</b>，源码版在 <b>C:\\KTRT\\data</b>。'
                   '里面是 ktrt.db（进度 / 收藏 / 造句 / 笔记 / 设置）、dictionary.db（ECDICT 离线词典）、'
                   'phrasal_verbs.json（动词短语库）、wordbooks（导入的词书副本）。', 'li'))
    story.append(P('- 备份 / 换电脑：把整个数据目录复制走即可；升级、重装不碰这个目录，数据不会丢。', 'li'))
    story.append(P('- 联网只有两处：AI 相关功能（发给<i>你自己配置的</i>厂商）和 edge-tts 朗读（发给微软语音服务）。'
                   '断网也能背词、查词典、闯关、记笔记、导出。', 'li'))

    story.append(P('十一、注意事项与常见问题', 'h'))
    story.append(P('- 不要同时开两个 KTRT；不要删 / 移 data 目录；导入或编辑词书前先关掉 Excel / WPS（文件被占用会写不回去）。', 'li'))
    story.append(P('- 改了设置或换了词书后界面没变化：按 <b>Ctrl + F5</b> 强制刷新页面；如果还不行，退出程序重开一次。', 'li'))
    story.append(P('- AI 报错：先点「测试 AI」看是不是 Key 填错 / 欠费 / 网络不通；换了网络或代理后重开程序再试。', 'li'))
    story.append(P('- 朗读没声音：edge-tts 需要联网，先确认网络；也可以到设置页换成「浏览器语音」离线朗读。', 'li'))
    story.append(P('- 网页打不开：确认程序启动完成（约 3 秒），手动访问 http://127.0.0.1:8000 ；'
                   '若提示端口被占用，说明已经有一个 KTRT 在跑。', 'li'))
    story.append(P('- 杀毒 / 网盘同步软件不要实时扫描数据目录，避免锁住数据库文件。', 'li'))
    story.append(P('- 词书里的音标 / 释义有错：用学词页的铅笔图标就地改，保存后会写回词书 Excel 对应行。', 'li'))
    return story


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--test-key', default='')
    args = ap.parse_args()

    register_fonts()
    styles = build_styles()
    out = os.path.abspath(args.out)
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title='KTRT 使用说明 v%s' % args.version, author='HoweyYueng')
    story = content(args.version, args.test_key, styles, doc.width)

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont('KTRT', 9)
        canvas.setFillColor(colors.HexColor('#9ca3af'))
        label = '内测版 · ' if args.test_key else ''
        canvas.drawString(2 * cm, 1.1 * cm, 'KTRT v%s · %s溯源词斩 · by HoweyYueng' % (args.version, label))
        canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, '第 %d 页' % doc_.page)
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print('PDF saved:', out)


if __name__ == '__main__':
    sys.exit(main())
