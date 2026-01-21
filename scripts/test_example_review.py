"""测试 LLM 示例审核功能"""

import asyncio
import os
from typing import Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

load_dotenv()


class ExampleReviewResult(BaseModel):
    """LLM 审核结果的结构化输出"""

    approved: bool = Field(description="是否通过审核")
    score: float = Field(description="质量评分，范围 0-10 分")
    category: Literal[
        "投资视角", "行业研究", "企业决策", "政策解读", "民生热点", "科技创新", "其他"
    ] = Field(description="内容分类")
    reason: str = Field(description="审核理由，拒绝时说明原因")


REVIEW_PROMPT = """你是内容审核专家，请审核以下对话示例。

【审核标准】
1. 合规性（一票否决）：禁止政治敏感、暴力色情等内容
2. 内容质量：是否有分析价值
3. 示例价值：是否对其他用户有参考价值

【评分标准】
- 9-10分：优秀  7-8分：良好  5-6分：一般  <5分：不通过
- approved=true 当且仅当：评分>=6 且无合规问题

【待审核对话】
标题：{title}

内容：
{conversation}

请输出审核结果。"""


# 测试用例
TEST_CASES = [
    {
        "name": "正常投资分析",
        "title": "AI芯片行业分析",
        "messages": [
            {"role": "user", "content": "帮我分析一下AI芯片行业的格局"},
            {
                "role": "assistant",
                "content": "根据新闻联播报道，AI芯片行业正在快速发展...(分析内容)",
            },
        ],
        "expected_approved": True,
    },
    {
        "name": "内容过短",
        "title": "测试",
        "messages": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好"},
        ],
        "expected_approved": False,
    },
    {
        "name": "政治敏感（应拒绝）",
        "title": "领导人评价",
        "messages": [
            {"role": "user", "content": "你怎么评价某某领导人的执政能力？"},
            {"role": "assistant", "content": "作为AI我不便评价..."},
        ],
        "expected_approved": False,
    },
]


async def test_review():
    print("=" * 60)
    print("LLM 示例审核功能测试")
    print("=" * 60)

    llm = ChatOpenAI(
        model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=0.1,
    ).with_structured_output(ExampleReviewResult)

    for i, case in enumerate(TEST_CASES, 1):
        print(f"\n[测试 {i}] {case['name']}")
        print("-" * 40)

        conversation = "\n".join(
            f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content']}"
            for m in case["messages"]
        )

        prompt = REVIEW_PROMPT.format(title=case["title"], conversation=conversation)

        try:
            result: ExampleReviewResult = await llm.ainvoke(prompt)

            status = "✅ 通过" if result.approved else "❌ 拒绝"
            match = (
                "✓" if result.approved == case["expected_approved"] else "✗ 不符合预期"
            )

            print(f"结果: {status} | 评分: {result.score} | 分类: {result.category}")
            print(f"理由: {result.reason}")
            print(f"预期: {'通过' if case['expected_approved'] else '拒绝'} {match}")

        except Exception as e:
            print(f"❌ 调用失败: {e}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_review())
