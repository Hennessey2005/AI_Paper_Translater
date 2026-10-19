# -*- coding: utf-8 -*-
import re
import sys
sys.stdout.reconfigure(encoding="utf-8")
md = open('output/paper_test/译文.zh.md', encoding='utf-8').read()
pairs = md.count('$$')
blocks = re.findall(r'\$\$(.+?)\$\$', md, flags=re.S)
print('$$ 字符数:', pairs, '→ 公式块:', len(blocks))
print('式(1):', (blocks[0][:120] + '…') if blocks else 'EMPTY')
print('式(11):', (blocks[-1][:120] + '…') if blocks else 'EMPTY')
titles = [l for l in md.split(chr(10)) if l.startswith('# ')]
print('一级标题:', titles)
