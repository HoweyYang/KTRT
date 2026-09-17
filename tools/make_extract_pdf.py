# -*- coding: utf-8 -*-
r"""生成「把单词书变成可导入的 Excel」说明 PDF（程序内 docs/guide_extract.pdf）。

用法（reportlab 在 Codex 运行时 python 里）：
  runtime_python tools/make_extract_pdf.py --version 0.2.0b --out frontend/static/docs/guide_extract.pdf

命名约定：输出文件名不带版本号，版本号只在页脚；发版时换 --version 重新生成即可。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from make_manual import build_styles, register_fonts


def code_box(text, width):
    style = ParagraphStyle('code', fontName='KTRT', fontSize=9, leading=14,
                           textColor=colors.HexColor('#1f2937'))
    tbl = Table([[Paragraph(text.replace('\n', '<br/>'), style)]], colWidths=[width])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f7fb')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    return tbl


def content(version, styles, width):
    def P(text, style='body'):
        return Paragraph(text, styles[style])

    story = []
    story.append(P('把单词书变成可导入的 Excel', 'title'))
    story.append(P('溯源词斩 KTRT（KillTimeRecitationTool）v%s · AI 扒取词书方法 · 开发者 HoweyYueng'
                   % version, 'sub'))
    story.append(P('目标：把任意单词书（PDF / 电子书 / 网页 / 图片扫描件）整理成 KTRT 的标准格式，导入后即可背诵。'))

    story.append(P('一、标准格式（11 列）', 'h'))
    rows = [['列名', '必填', '说明']] + [
        ['【单词】', '是', '英文单词或短语'],
        ['【音标】', '否', 'IPA，可留空'],
        ['【词性释义】', '否', '如 n. 名词；v. 动词'],
        ['【搭配】', '否', '多条用中文分号「；」分隔'],
        ['【短语】', '否', '多条用「；」分隔'],
        ['【同义词】', '否', '多条用「；」分隔'],
        ['【反义词】', '否', '多条用「；」分隔'],
        ['【同根词】', '否', '派生词族'],
        ['【List】', '否', '第几单元 / List，缺省为 1'],
        ['【语言】', '否', '英语 / 法语…，决定朗读语音'],
        ['【单词书】', '否', '书名，留空则用文件名'],
    ]
    tbl = Table([[Paragraph(c, ParagraphStyle('c', fontName='KTRT' if i else 'KTRT-Bold',
                                              fontSize=9.5, leading=14,
                                              textColor=colors.HexColor('#1f2937'))) for c in row]
                 for i, row in enumerate(rows)],
                colWidths=[width * 0.24, width * 0.10, width * 0.66])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef2ff')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 4))
    story.append(P('必填只有【单词】；多值字段用中文分号「；」分隔，导入后会拆成一行里的多个条目。列可以少，但不能改名字。', 'tip'))

    story.append(P('二、三种来源怎么处理', 'h'))
    story.append(P('<b>A · 纯单词列表（最省事）</b>：每行一个词，存成 .txt 或 .csv 直接导入；也可以用 Tab 分隔「单词 / 音标 / 释义」三列。', 'li'))
    story.append(P('<b>B · 电子书（EPUB / 网页 / 可复制的 PDF）</b>：打开后把单词表区域复制成文本 → 粘贴给 AI（DeepSeek / ChatGPT 等），'
                   '用下面的提示词提取 → 把 AI 输出的表格粘进 Excel / WPS，存成 .xlsx。', 'li'))
    story.append(P('<b>C · 扫描版 PDF（图片）</b>：先 OCR（WPS / Office 自带 OCR，或用能转文本的工具），拿到文本后同 B 处理。', 'li'))

    story.append(P('三、可直接复制的 AI 提示词', 'h'))
    story.append(KeepTogether([P('提示词 1 · 从文本提取为标准词表', 'body'), code_box(
        '你是英语词汇整理助手。下面是一份单词表文本（可能排版混乱、夹杂序号和无关内容）。\n'
        '请提取所有英文单词，整理成表格，每行一个词，包含：单词、音标（IPA，没有就留空）、\n'
        '词性+中文释义。列名严格使用：【单词】【音标】【词性释义】。\n'
        '删除序号、页眉页脚、广告、重复词。只输出表格内容，不要解释。\n\n'
        '文本如下：\n<<在这里粘贴单词表文本>>', width)]))
    story.append(Spacer(1, 6))
    story.append(KeepTogether([P('提示词 2 · 按章节 / List 分组', 'body'), code_box(
        '继续上面的表格，新增两列【List】和【单词书】。\n'
        '【List】按原文的单元/章节编号填写（没有就都填 1）；\n'
        '【单词书】填 <<书名>>；【语言】填 英语。输出完整表格。', width)]))
    story.append(Spacer(1, 6))
    story.append(KeepTogether([P('提示词 3 · 批量补全音标 / 搭配 / 短语 / 同反义词 / 同根词', 'body'), code_box(
        '你是英语词汇编辑。下面每个词，请输出：\n'
        'p=国际音标；c=2个常见搭配；ph=2个常见短语；s=2个同义词；\n'
        'a=1-2个反义词（没有就写空数组）；r=2-3个同根词。\n'
        '只输出一个 JSON 对象，不要任何其他文字：\n'
        '{"单词": {"p":"音标","c":["搭配1","搭配2"],"ph":["短语1","短语2"],\n'
        '"s":["同义1","同义2"],"a":["反义1"],"r":["同根1","同根2"]}, ...}\n\n'
        '词表：<<粘贴单词列表>>', width)]))

    story.append(P('四、保存与导入', 'h'))
    story.append(P('1. 把 AI 输出的内容粘进 Excel / WPS：第一行列名，第二行起数据。', 'li'))
    story.append(P('2. 另存为 .xlsx。', 'li'))
    story.append(P('3. 在 KTRT「导入」页上传该文件；书名可留空（用表内【单词书】列或文件名）。', 'li'))
    story.append(P('4. 导入成功后，「学词」页下拉即可看到这本书。', 'li'))

    story.append(P('五、小技巧', 'h'))
    story.append(P('- 想先试水：只做【单词】+【词性释义】两列就能导入。', 'li'))
    story.append(P('- 想省事：把 EPUB 转成文本，让 AI 一次跑完「提示词 1 + 提示词 3」，提取与补全一步到位。', 'li'))
    story.append(P('- 想更省：直接把单词书丢给本地 AI，让它按上面的格式整理成 Excel，再导入。', 'li'))
    story.append(P('- 发现词书里音标或释义有误：在「学词」页用铅笔图标就地改，保存会写回词书 Excel 对应行。', 'li'))
    return story


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    register_fonts()
    styles = build_styles()
    out = os.path.abspath(args.out)
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title='把单词书变成可导入的 Excel', author='HoweyYueng')
    story = content(args.version, styles, doc.width)

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont('KTRT', 9)
        canvas.setFillColor(colors.HexColor('#9ca3af'))
        canvas.drawString(2 * cm, 1.1 * cm, 'KTRT v%s · 溯源词斩 · by HoweyYueng' % args.version)
        canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, '第 %d 页' % doc_.page)
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print('PDF saved:', out)


if __name__ == '__main__':
    sys.exit(main())
