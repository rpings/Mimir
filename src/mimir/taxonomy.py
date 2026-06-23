"""AI taxonomy — 10 topics for LLM classification."""

from __future__ import annotations

from mimir.models import TopicDef

TOPICS: list[TopicDef] = [
    TopicDef(
        id="ai_agent",
        name="AI Agent",
        description="Autonomous agents, multi-agent collaboration, tool use, MCP protocol, agent frameworks (LangGraph, AutoGen, CrewAI).",
    ),
    TopicDef(
        id="rag",
        name="RAG / 检索增强",
        description="Retrieval-Augmented Generation, vector databases, embedding models, reranking, hybrid search, knowledge base construction.",
    ),
    TopicDef(
        id="inference",
        name="推理优化",
        description="LLM inference optimization, quantization (GPTQ/AWQ/GGUF), speculative decoding, KV cache, vLLM, TensorRT-LLM, edge deployment.",
    ),
    TopicDef(
        id="multimodal",
        name="多模态",
        description="Vision-language models (VLM), text-to-image/video generation, speech/audio AI, multimodal understanding and generation.",
    ),
    TopicDef(
        id="training",
        name="训练与微调",
        description="Pre-training, fine-tuning (LoRA/QLoRA), RLHF/DPO alignment, synthetic data, curriculum learning, distributed training.",
    ),
    TopicDef(
        id="safety",
        name="安全与对齐",
        description="Red teaming, jailbreak defense, mechanistic interpretability, AI content safety, watermarking, AI regulation and policy.",
    ),
    TopicDef(
        id="infra",
        name="基础设施",
        description="GPU hardware, AI chips, distributed systems, model serving platforms, AI infrastructure and operations (LLMOps).",
    ),
    TopicDef(
        id="ai_coding",
        name="AI Coding",
        description="AI-assisted software engineering, code generation, autonomous debugging, SWE-bench, Copilot, Claude Code, coding agents.",
    ),
    TopicDef(
        id="open_models",
        name="开源模型",
        description="Open-source model releases, model weights, benchmark results, model comparisons, HuggingFace trending models.",
    ),
    TopicDef(
        id="industry",
        name="行业动态",
        description="AI industry news, product launches, startup funding, M&A, corporate strategy, talent movement.",
    ),
]

TOPIC_BY_ID: dict[str, TopicDef] = {t.id: t for t in TOPICS}


def taxonomy_text() -> str:
    """Generate the taxonomy listing for the LLM system prompt."""
    lines = ["AI Topic Taxonomy:", ""]
    for t in TOPICS:
        lines.append(f"- {t.id}: {t.name} — {t.description}")
    return "\n".join(lines)


def topic_ids() -> list[str]:
    return [t.id for t in TOPICS]
