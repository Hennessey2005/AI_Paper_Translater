# -*- coding: utf-8 -*-
import json
import sys
sys.stdout.reconfigure(encoding="utf-8")
segs = json.load(open('output/paper_test/segments.json', encoding='utf-8'))
for s in segs:
    if s['kind'] == 'title':
        print(s['seg_id'], f"p{s['page_idx']}b{s['block_index']}", '|', s.get('src', '')[:60])
