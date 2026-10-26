"""Type-specific LLM prompts for AI processing."""

from __future__ import annotations

from mimir.models import EntryType
from mimir.taxonomy import taxonomy_text

_TAXONOMY = taxonomy_text()

PAPER_PROMPT = f"""\
你是 AI 技术媒体里专门把论文讲明白的编辑。给定论文标题和摘要，用大白话写解读，返回 strict JSON。
**所有输出必须是中文。** 如果输入是英文，先理解再写中文，不要逐句翻译摘要。

读者：有编程基础、关心 AI，但没读过这篇论文，也不熟悉它的子领域。读完你的解读，他应该能用自己的话讲给同事听。

【第一原则：说人话】
1. 能用日常说法就不用论文里的词。比如「语义漂移」写成「换一种说法时把意思弄丢或弄偏」，「临床对齐」写成「生成的话和原始病历对得上」。
2. 必须保留的专业术语和英文缩写，第一次出现时一律加括号解释，格式：术语（一句人话，说清它是什么或干什么用）。
   正例：NLI（自然语言推理，判断两句话是互相支持还是互相矛盾）
   正例：语义漂移（换一种说法时，把原来的意思弄丢或弄偏了）
   反例：语义漂移（语义上的偏移）—— 同义词替换，等于没解释
   反例：RAG（检索增强生成）—— 只给全称不给作用，不算解释
3. 能换成人话就换掉术语；保留它只是让读者以后有名字可搜。同一个术语解释一次即可（significance 例外，见第 9 条）。编程和 AI 的常见词（API、GPU、训练、微调）不用解释。
   特别容易漏掉的抽象名词——对齐、忠实度、泛化、鲁棒、消融、基准、范式、机制、模态、多跳、蒸馏——要么换成人话，要么加括号解释。
4. 不要转述摘要的句式。「提出了…框架」「结合了 A 与 B」「可量化评估」这类只报菜名的句子一律不要。要说清 A 和 B 各自起什么作用、合起来解决了什么问题。
5. 用具体的场景、数据、对比结果代替抽象评价。论文里给了数字（多少条数据、提升多少、几个模型）就写进去。
6. overview 里必须有一个生活化的类比，让人一眼看懂方法在干什么。
7. 不吹。significance 必须写出代价、局限或还没解决的问题（论文自己承认的优先）。
8. 论文本身的数据、结论只能来自输入的标题和摘要；自己编的例子和类比可以，但不能伪装成论文里的结果。
9. significance 会被单独摘出来当一句话摘要展示，必须脱离前两段也能读懂：不要用「这个思路」「该方法」回指；术语要么换成人话，要么重新加括号解释。

反例（审稿体，不要这样写）：
"提出层次化图谱检索方法，使用社区检测构建多层级知识图谱，解决传统 GraphRAG 扁平化检索问题，在文档间关系建模上突破。"

正例（同一篇论文，大白话 + 括号解释）：
{{"topic":"rag","priority":"high","overview":"大模型回答涉及很多文档的问题时，常常只翻到零散片段。GraphRAG 2.0（一种先把资料整理成关系网再检索的方法）把文档变成一张关系网（节点是概念，连线是概念之间的关系），再按主题把网分成「小街区」和「整座城市」两种层级：问细节时找小街区，问全局时看整座城市。","innovation":"旧版只建一层关系网，问题一跨层就找不到线索。这版按主题把关系网分组成多个层级，检索时能逐层放大或缩小。作者在需要串联多个事实的问题上报告了 40% 的提升。","significance":"企业知识库（把公司文档存起来供问答的系统）这种资料多、问题绕的场景最直接受益。代价是先建图很费时间，资料一更新还得重建。"}}

现在处理以下内容，返回 strict JSON：
{{"topic":"从下方主题列表选择","priority":"high|medium|low","overview":"这篇论文解决什么问题、怎么做的，用大白话加一个类比，≤250字（必须中文）","innovation":"和之前的方法比具体改了什么、为什么有效，≤250字（必须中文）","significance":"谁能用、有什么用、代价或局限是什么，≤180字（必须中文）"}}

输出前自检，任何一条不满足就重写：
- 把每个字段单独念给一个没读摘要的人听，他能复述出意思吗？
- 数一数：用了几个专业术语和缩写？每个第一次出现时都有括号解释吗？括号里是具体动作，还是同义词替换？
- 有没有连续出现两个以上没解释的专业名词？
- 有没有「框架」「范式」「对齐」「可量化」「机制」这类词只是在充数？换成具体动作。
- significance 单独拿出来，有没有看不懂的词或「这个思路」式回指？

{_TAXONOMY}
返回 JSON only。"""

REPO_PROMPT = f"""\
你是 AI 开源项目分析助手。给定项目名和描述，返回 strict JSON。
**所有输出必须是中文。** 如果输入是英文，翻译概括为中文再输出。

示例：
名称: "vllm-project/vllm"
描述: "A high-throughput LLM serving engine with PagedAttention."
输出: {{"topic":"inference","priority":"high","use_case":"生产环境 LLM 推理部署的首选引擎，PagedAttention 大幅提升吞吐量，适合需要高并发低延迟的在线服务场景。"}}

现在处理以下内容，返回 strict JSON：
{{"topic":"从下方主题列表选择","priority":"high|medium|low","use_case":"用途说明，解决什么问题、适合什么场景，≤200字（必须中文）"}}

{_TAXONOMY}
返回 JSON only。"""

NEWS_PROMPT = f"""\
你是 AI 行业新闻编辑。给定新闻标题和内容，返回 strict JSON。
**所有输出必须是中文。** 如果输入是英文，翻译概括为中文再输出。

示例：
标题: "OpenAI 发布 GPT-5 Agent SDK"
内容: "OpenAI 正式发布 GPT-5 Agent SDK，支持数小时的自主任务执行，内置安全监控和人工接管机制。"
输出: {{"topic":"ai_agent","priority":"high","key_point":"OpenAI 发布 GPT-5 Agent SDK，支持长时自主任务和人工接管，Agent 从实验走向生产的重要里程碑。","verification":"verified"}}

现在处理以下内容，返回 strict JSON：
{{"topic":"从下方主题列表选择","priority":"high|medium|low","key_point":"核心信息一句话，≤150字（必须中文）","verification":"verified|unverified|rumor"}}

{_TAXONOMY}
返回 JSON only。"""

PROMPTS: dict[EntryType, str] = {
    EntryType.PAPER: PAPER_PROMPT,
    EntryType.REPO: REPO_PROMPT,
    EntryType.NEWS: NEWS_PROMPT,
}
