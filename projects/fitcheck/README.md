# fitcheck · 合身判定系统

买衣服前用净体数据 + 成衣尺码表，算出紧/松、下摆落点、袖长落点。纯算术 + 规则引擎，不依赖生成模型。

## 产物在哪

代码、量法规范、测试、数据都在 deliverables/fitcheck/：

- run.py —— 入口
- engine/ —— 判定引擎（ease 松量、rules 规则、calibrate 标定、validate 校验）
- render/card.py —— 判定卡渲染
- 01-量法规范.html —— 12 部位量法图解
- tests/test_assertions.py —— 25 条验收断言
- data/ —— 身体数据（body.json）与成衣样本

## 当前进度

见 current.md。核心：P0 量法 + P1 判定引擎已完成并经两轮实穿验证；待做短袖路径实测、骨点肩宽实测、个人标定攒样本（2/5）。

## 续接前必读

1. README.md（本文件，入口）
2. current.md（进度与下一步）
3. memory.md（本项目独立记忆）
