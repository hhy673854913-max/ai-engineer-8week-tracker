# week-04 审校结果

## 周总评

M2 的工程主线（需求→数据→链路→界面）岗位落点扎实：非目标的面试价值、`effective_from` 消灭"答旧规则"、Badcase A–G 决策树、trace_id/成本指标、拒答演示与 `v-html` 攻击面都指向真实生产与面试追问。问题集中在 Day 16–17 的 LangChain 概念层：LCEL、三个 OutputParser、四个组合件被当作已知语法直接使用，既没有定义也没有说明它们在 Agent 工程中的位置；最典型的是 Day 17 上午用 LCEL 拼"可变长链"（`compose` 并非 LangChain API）、下午又回到手写 if，形成断点。Day 18 的架构图缺一句"这张图在你整体链路/面试里怎么讲"。建议按"每个 LangChain 概念补一句定义 + 一句岗位对位"的方式收口。

## day-16 · LangChain 快速上手与复刻 mini-RAG

- **P0 · 3. LCEL：用管道符组合** ｜ 问题：这一节（以及 Day 17 全篇）始终没有一句话定义 LCEL，只写了「`|` 的本质是 `__or__` 重载，把前一个 Runnable 的输出喂给下一个」。读者能照抄 `prompt | llm | StrOutputParser()`，却答不出「LCEL 是什么、为什么要有这一层」；而 Day 17 又以「LCEL 进阶」「LCEL 的四个组合件」继续使用它。｜ 建议补写：**LCEL（LangChain Expression Language）是 LangChain 的链式编排 DSL**：凡是实现了 `Runnable` 协议的对象（提示词、模型、检索器、普通函数）都能用 `|` 拼成一条链，并自动获得 `invoke / batch / stream / astream` 四种调用方式——你在 M2 里做到「同一个问答逻辑既能跑评测批处理、又能给前端流式吐字」，靠的就是这层协议。面试被问「LangChain 和 LangGraph 什么关系」时，标准答法就是：LCEL 负责线性组合，LangGraph 负责有状态的分支与循环。

- **P1 · 2. LangChain 的四个核心抽象** ｜ 问题：「输出层：`StrOutputParser`、`JsonOutputParser`、`PydanticOutputParser`」一句并列三个类，从没说三者的区别和使用时机。读者不知道 `JsonOutputParser` 只保证是合法 JSON、字段对不对不管，而 `PydanticOutputParser` 会校验成模型；也不知道这正是 Agent 里「模型输出→结构化参数」的命门（Day 22 工具调用直接依赖它）。｜ 建议补写：三个 Parser 的选择线：`StrOutputParser` 只要纯文本；`JsonOutputParser` 只保证输出是合法 JSON，字段对不对不管；`PydanticOutputParser` 会把 JSON 直接校验成你第 1 周写的那个 `BaseModel`，字段缺失或类型错立刻报错——Day 22 让模型返回工具调用参数、Day 30 让多个 Agent 交换结构化结果，用的都是它。选错的典型事故是：下游 `data["tool_args"]` 拿到的是字符串不是 dict，直到线上才炸。

## day-17 · LCEL 进阶与可配置检索链

- **P1 · 3. LCEL 的四个组合件** ｜ 问题：整节是一张「组件 / 用途 / 例子」表格，只讲清「能这么组合」，没有一句说明 AI Agent 工程师为什么必须掌握它们、它们在后面的 Agent 链路里对应什么动作。读者学完只会照抄 `RunnableBranch`，真要判断「这里该不该用条件路由」仍然只能凭感觉。｜ 建议补写：这四个件不是 LangChain 的语法糖，而是 Agent 编排的四种基本动作：`RunnableParallel` 对应「一次问三个改写后的 query / 并行调两个工具」；`RunnableBranch` 对应「有历史就改写、没历史就原样」的路由决策，Day 24 LangGraph 的条件边就是把它画进了图里；`RunnablePassthrough.assign` 对应「给 Agent 的状态追加检索结果」。面试被问「你怎么做条件路由和多路召回」，答的就是这四个动作的取舍与代价。

- **P1 · 4. 可配置链的结构** ｜ 问题：示例代码 `return compose(steps)` 里的 `compose` 并不是 LangChain 的 API，全文也没定义，`steps.append(...)` 还用省略号带过——照着写必然 NameError。更大的断点是：下午任务 2 的 `RagPipeline` 里根本没有 LCEL，而是手写 `if`。上午教的「用 LCEL 拼可变长链」在后续所有代码里彻底消失。｜ 建议补写：`compose` 不是 LangChain 提供的函数，可变长链要自己拼：`from functools import reduce; chain = reduce(lambda a, b: a | b, steps)`（等价于手动构造 `RunnableSequence`）。但生产代码里更常见的是任务 2 那种手写 `if`——因为「哪几步开着」本质是业务分支，用 `if` 更好读、更好打日志、更好做灰度；LangGraph（Day 24）做的事就是把这堆 `if` 显式画成图，让状态和回放可控。面试被问「为什么不全用链式」，这就是你的答案。

## day-18 · M2 设计：领域知识库问答

- **P1 · 3. 架构** ｜ 问题：这一节只有一张 mermaid 图，没有任何文字说明。紧接着 §4 说 `effective_from/to` 是「灵魂」，可图里根本没有「按有效期过滤」这个节点——读者无法把这个字段对应到链路哪一步生效；图中的「拒答 + 推荐相近条目」「引用校验」与 Day 14 七步链路之间，也没有一句过渡说明。｜ 建议补写：这张图就是 Day 14 七步链路的工程版：离线侧多了一条「分块 → 嵌入 → 双索引（向量 + BM25）」的索引流水线；在线侧要在 `RW` 之前加一个 `FILTER[按 effective_from/to 过滤过期文档]` 节点——过期文档根本不进候选集，「答旧规则」这一大类 badcase 就消失了，§4 的「灵魂」字段是在这一步生效的。面试讲 M2 时按「离线 / 在线」两层讲，每个节点先说它挡掉哪类 badcase、再说取舍，这张图就是你白板上画的那条主线。

## day-19 · M2 开发（一）：问答链路与 Badcase 记录

无

## day-20 · M2 开发（二）：引用溯源界面与演示

无
