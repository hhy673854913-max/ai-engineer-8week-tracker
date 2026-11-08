# 学习留痕

这个目录是 40 天的"学习日记"，也是八周之后你面试时讲 badcase 与取舍的原始素材。

## 怎么打卡

```powershell
# 生成第 12 天的日志（自动填日期、标题、课程链接）
python scripts/checkin.py 12

# 看整体进度
python scripts/checkin.py --status
```

规则只有三条：

1. **每天提交一次**，commit message 写清"做了什么"，不要 `update`。
2. **写卡点**，不要只写"今天学了 X"。卡点才是你以后能讲的故事。
3. **答 2–3 道思考题**，用自己的话，不要抄课程文档。

## 目录

```
logs/
├─ TEMPLATE.md      日志模板
├─ day-01.md …      每天一份（checkin 生成）
└─ index.md         本文件
```

> 不想公开自己的日志？把 `logs/day-*.md` 加进 `.gitignore` 即可——但那样就失去了"留痕"的意义。
> 建议公开：持续 40 天的 commit 记录，本身就是最好的能力证明。
