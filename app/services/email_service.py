"""邮件服务 - 163邮箱SMTP"""

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from loguru import logger

from app.core.config import settings


async def send_verification_email(to_email: str, code: str) -> bool:
    """
    发送验证码邮件

    Args:
        to_email: 收件人邮箱
        code: 6位验证码

    Returns:
        是否发送成功
    """
    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("SMTP未配置，跳过邮件发送（开发模式）")
        logger.info(f"[DEV] 验证码: {code} -> {to_email}")
        return True

    subject = f"【{settings.smtp_from_name}】邮箱验证码"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
            .container {{ max-width: 500px; margin: 0 auto; padding: 40px 20px; }}
            .code {{ 
                font-size: 32px; 
                font-weight: bold; 
                letter-spacing: 8px; 
                color: #333;
                background: #f5f5f5;
                padding: 20px 30px;
                border-radius: 8px;
                text-align: center;
                margin: 30px 0;
            }}
            .footer {{ color: #999; font-size: 12px; margin-top: 40px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>邮箱验证</h2>
            <p>您正在进行账号注册，验证码为：</p>
            <div class="code">{code}</div>
            <p>验证码 {settings.verification_code_expire_minutes} 分钟内有效，请勿泄露给他人。</p>
            <p>如非本人操作，请忽略此邮件。</p>
            <div class="footer">
                <p>此邮件由系统自动发送，请勿回复。</p>
            </div>
        </div>
    </body>
    </html>
    """

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_user}>"
    message["To"] = to_email

    text_part = MIMEText(
        f"您的验证码是: {code}，{settings.verification_code_expire_minutes}分钟内有效。",
        "plain",
        "utf-8",
    )
    html_part = MIMEText(html_content, "html", "utf-8")

    message.attach(text_part)
    message.attach(html_part)

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            use_tls=True,
        )
        logger.info(f"验证码邮件已发送: {to_email}")
        return True
    except Exception as e:
        logger.error(f"发送邮件失败: {e}")
        return False
