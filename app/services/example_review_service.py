"""使用示例审核服务 - 使用 LLM 自动审核用户提交的示例"""

import os
from datetime import datetime, UTC
from typing import Literal, Optional, List

from langchain_openai import ChatOpenAI
from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.example import ExampleSubmission
from app.models.chat import ChatSession, ChatMessage


class ExampleReviewResult(BaseModel):
    """LLM 审核结果的结构化输出"""

    approved: bool = Field(description="是否通过审核")
    score: float = Field(ge=0, le=10, description="质量评分 0-10")
    category: Literal[
        "投资视角", "行业研究", "企业决策", "政策解读", "民生热点", "科技创新", "其他"
    ] = Field(description="内容分类")
    reason: str = Field(description="审核理由，拒绝时说明原因")


REVIEW_SYSTEM_PROMPT = """你是一位内容审核专家，负责审核用户提交的新闻分析对话示例。

【审核标准】

1. **合规性**（一票否决 - 最高优先级）
   ⚠️ 严格禁止任何涉及以下内容的示例，只要触及必须拒绝：
   - 负面评价国家领导人、政府机构或执政党
   - 涉及敏感政治话题（如台湾、西藏、新疆、香港等主权和治理问题）
   - 传播未经证实的政治谣言或阴谋论
   - 涉及宗教敏感、民族矛盾内容
   - 暴力、色情、赌博、违法犯罪内容
   - 散布恐慌、煽动情绪的内容
   - 涉及军事机密或国家安全的敏感信息
   
   ✅ 只要涉及上述任何一条，必须：approved=false，score<=3

2. **内容质量**（权重40%）
   - 对话是否有实际分析价值和深度
   - 提问是否清晰明确、回答是否专业有见地
   - 是否能帮助其他用户理解产品功能和新闻分析方法

3. **示例价值**（权重30%）
   - 是否展示了产品的典型使用场景
   - 是否对其他用户有学习和参考价值
   - 是否具有一定的代表性和普适性

4. **内容完整性**（权重30%）
   - 对话是否完整（至少2轮有效对话）
   - 回答是否包含有价值的分析结论和数据支撑
   - 是否有清晰的逻辑结构

【分类规则】
- 投资视角：股市分析、行业投资机会、经济趋势、财经数据解读
- 行业研究：特定行业深度分析、产业链研究、竞争格局
- 企业决策：企业战略分析、商业决策参考、市场机会
- 政策解读：政策分析、法规解读、政府工作报告解读
- 民生热点：就业、教育、医疗、住房、社会保障等民生话题
- 科技创新：科技进展、技术应用、数字经济、人工智能
- 其他：不属于以上分类的内容

【评分标准】
- 9-10分：优秀示例，分析深入、见解独到、对用户极具参考价值
- 7-8分：良好示例，内容充实、逻辑清晰、值得推荐
- 5-6分：一般示例，基本合格但亮点不足
- 5分以下：质量不足或存在问题，不予通过

【通过条件】
- approved=true 当且仅当：评分>=6 且 无任何合规问题
- 有任何合规风险时，宁可误杀不可放过

【输出要求】
- 必须给出具体、有建设性的审核理由
- 拒绝时需明确指出问题所在
- 分类要准确匹配内容主题"""


class ExampleReviewService:
    """使用示例审核服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._llm = None

    @property
    def llm(self):
        """懒加载 LLM 实例"""
        if self._llm is None:
            base_llm = ChatOpenAI(
                model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4"),
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv(
                    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
                ),
                temperature=0.1,
            )
            self._llm = base_llm.with_structured_output(ExampleReviewResult)
        return self._llm

    async def get_pending_submissions(self, limit: int = 5) -> List[ExampleSubmission]:
        """获取待审核的提交"""
        query = (
            select(ExampleSubmission)
            .where(ExampleSubmission.status == "pending")
            .order_by(ExampleSubmission.submitted_at.asc())
            .limit(limit)
        )
        result = await self.session.exec(query)
        return list(result.all())

    async def get_session_with_messages(
        self, session_id: int
    ) -> tuple[Optional[ChatSession], List[ChatMessage]]:
        """获取会话及其消息"""
        chat_session = await self.session.get(ChatSession, session_id)
        if not chat_session:
            return None, []

        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        result = await self.session.exec(query)
        return chat_session, list(result.all())

    async def review_example(
        self, title: str, messages: List[ChatMessage]
    ) -> ExampleReviewResult:
        """使用 LLM 审核示例"""
        conversation_text = "\n\n".join(
            [
                f"{'【用户】' if m.role == 'user' else '【AI助手】'}: {m.content[:800]}"
                for m in messages[:10]
            ]
        )

        prompt = f"""请审核以下用户提交的新闻分析对话示例：

【对话标题】
{title}

【对话内容】
{conversation_text}

请根据审核标准进行评估，输出审核结果。"""

        messages_for_llm = [
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            result = await self.llm.ainvoke(messages_for_llm)
            return result
        except Exception as e:
            logger.error(f"LLM 审核失败: {e}")
            return ExampleReviewResult(
                approved=False,
                score=0,
                category="其他",
                reason=f"审核服务异常: {str(e)}",
            )

    async def process_submission(self, submission: ExampleSubmission) -> bool:
        """处理单个提交"""
        submission.status = "reviewing"
        await self.session.commit()

        chat_session, messages = await self.get_session_with_messages(
            submission.chat_session_id
        )

        if not chat_session or len(messages) < 2:
            submission.status = "rejected"
            submission.llm_reason = "会话不存在或消息数量不足"
            submission.llm_score = 0
            submission.reviewed_at = datetime.now(UTC)
            await self.session.commit()
            return False

        result = await self.review_example(chat_session.title, messages)

        submission.llm_score = result.score
        submission.llm_category = result.category
        submission.llm_reason = result.reason
        submission.reviewed_at = datetime.now(UTC)

        if result.approved:
            submission.status = "approved"
            # 更新 ChatSession 为精选
            chat_session.is_featured = True
            chat_session.featured_category = result.category
            chat_session.featured_contributor = submission.display_name
            # 确保会话是公开的
            if not chat_session.is_public:
                chat_session.is_public = True
                if not chat_session.share_token:
                    chat_session.share_token = ChatSession.generate_share_token()
            logger.info(
                f"✓ 示例审核通过: {chat_session.title} | 分类: {result.category} | 评分: {result.score}"
            )
        else:
            submission.status = "rejected"
            logger.info(f"✗ 示例审核拒绝: {chat_session.title} | 原因: {result.reason}")

        await self.session.commit()
        return result.approved

    async def process_queue(self, limit: int = 5) -> dict:
        """处理审核队列"""
        stats = {"processed": 0, "approved": 0, "rejected": 0, "errors": 0}

        submissions = await self.get_pending_submissions(limit)
        if not submissions:
            logger.info("审核队列为空")
            return stats

        logger.info(f"开始处理 {len(submissions)} 个待审核示例")

        for submission in submissions:
            try:
                approved = await self.process_submission(submission)
                stats["processed"] += 1
                if approved:
                    stats["approved"] += 1
                else:
                    stats["rejected"] += 1
            except Exception as e:
                logger.error(f"处理提交 {submission.id} 失败: {e}")
                submission.status = "pending"  # 重置状态以便重试
                await self.session.commit()
                stats["errors"] += 1

        logger.info(
            f"审核完成 - 处理: {stats['processed']} | "
            f"通过: {stats['approved']} | 拒绝: {stats['rejected']} | 错误: {stats['errors']}"
        )
        return stats
