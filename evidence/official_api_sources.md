# 本批API协议查阅

查阅日期：2026-10-19。仅为文档查阅，不是实际API请求或模型能力证明。

- DeepSeek官方：[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)。采用Chat Completions的function工具结构与JSON arguments；strict Beta需单独支持和验证，本包不默认启用。实际model/工具/视觉能力依配置与probe结果，不从品牌名称猜测。
- OpenAI官方：[Function calling](https://developers.openai.com/api/docs/guides/function-calling)。本包实现工具schema及参数本地校验；只返回调用建议，正式执行仍必须通过已确认任务契约。当前适配Chat Completions，不声称覆盖所有模型和API。

未抓取用户遥感实验数据，未下载实验影像，未新增GitHub协作要求。模型费用需配置官方价格来源，不内置可能变化的单价。
