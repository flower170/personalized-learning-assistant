"""
讯飞 Spark API 配置模块
集中管理所有模型配置（REST API 格式）
"""
import os
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 加载 .env 文件
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())
    except Exception as e:
        logger.warning(f"加载 .env 文件失败: {e}")


def _read_env(key: str, default: str = "") -> str:
    val = os.environ.get(key, "")
    # 处理 ${VAR} 引用
    if val.startswith("${") and val.endswith("}"):
        val = os.environ.get(val[2:-1], default)
    return val or default


@dataclass
class SparkModelConfig:
    """模型配置（兼容讯飞/智谱等多提供商）"""
    name: str                # 显示名称
    domain: str              # API 请求中的 model 字段值
    api_url: str             # API 地址
    app_id: str = ""
    api_key: str = ""
    api_secret: str = ""
    provider: str = "xunfei" # xunfei: Bearer api_key:api_secret; zhipu: Bearer api_key
    available: bool = True   # 模型是否开通可用


class Settings:
    """全局配置"""

    APP_ID: str = _read_env("SPARK_APP_ID") or _read_env("XUNFEI_APP_ID", "")
    API_KEY: str = _read_env("SPARK_API_KEY") or _read_env("XUNFEI_API_KEY", "")
    API_SECRET: str = _read_env("SPARK_API_SECRET") or _read_env("XUNFEI_API_SECRET", "")

    # ========== 以下模型已开通 ==========

    # spark-pro — 主力模型
    SPARK_PRO: SparkModelConfig = SparkModelConfig(
        name="spark-pro", domain="pro",
        api_url="https://spark-api-open.xf-yun.com/v1/chat/completions",
        app_id=APP_ID, api_key=API_KEY, api_secret=API_SECRET,
    )

    # spark-lite — 轻量模型
    SPARK_LITE: SparkModelConfig = SparkModelConfig(
        name="spark-lite", domain="lite",
        api_url="https://spark-api-open.xf-yun.com/v1/chat/completions",
        app_id=APP_ID, api_key=API_KEY, api_secret=API_SECRET,
    )

    # spark-x2-flash — Agent 专用模型（OpenAI 兼容协议）
    SPARK_X2_FLASH: SparkModelConfig = SparkModelConfig(
        name="spark-x2-flash", domain="spark-x",
        api_url="https://spark-api-open.xf-yun.com/agent/v1/chat/completions",
        app_id=APP_ID, api_key=API_KEY, api_secret=API_SECRET,
    )

    # spark-max-32k — 32K超长上下文（已开通）
    SPARK_MAX_32K: SparkModelConfig = SparkModelConfig(
        name="spark-max-32k", domain="max-32k",
        api_url="https://spark-api-open.xf-yun.com/v1/chat/completions",
        app_id=APP_ID, api_key=API_KEY, api_secret=API_SECRET,
    )

    # generalv3 — 基础版
    SPARK_GENERALV3: SparkModelConfig = SparkModelConfig(
        name="spark-generalv3", domain="generalv3",
        api_url="https://spark-api-open.xf-yun.com/v1/chat/completions",
        app_id=APP_ID, api_key=API_KEY, api_secret=API_SECRET,
    )

    # spark-4.0-ultra — 已授权旗舰模型（实测 v1 端点可用，用于资源生成）
    SPARK_ULTRA: SparkModelConfig = SparkModelConfig(
        name="spark-4.0-ultra", domain="4.0Ultra",
        api_url="https://spark-api-open.xf-yun.com/v1/chat/completions",
        app_id=APP_ID, api_key=API_KEY, api_secret=API_SECRET,
    )

    # ========== GLM（智谱 AI）— OpenAI 兼容接口 ==========
    GLM_API_KEY: str = _read_env("GLM_API_KEY", "e1970f97f8694f598dd39f5a39ca8b6f.nNpKraj4zf1r5Vc9")
    GLM_API_URL: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # glm-4.7-flash — 用户指定资源生成模型
    GLM_4_7_FLASH: SparkModelConfig = SparkModelConfig(
        name="glm-4.7-flash", domain="glm-4.7-flash",
        api_url=GLM_API_URL, api_key=GLM_API_KEY, provider="zhipu",
    )

    # glm-4.5-flash — 兜底（4.7 访问量过大/不可用时自动降级）
    GLM_4_5_FLASH: SparkModelConfig = SparkModelConfig(
        name="glm-4.5-flash", domain="glm-4.5-flash",
        api_url=GLM_API_URL, api_key=GLM_API_KEY, provider="zhipu",
    )

    # glm-4-flash — 非推理快模型（~1s），用于画像对话轮（抽取仍用 4.5-flash 保质量）
    GLM_4_FLASH: SparkModelConfig = SparkModelConfig(
        name="glm-4-flash", domain="glm-4-flash",
        api_url=GLM_API_URL, api_key=GLM_API_KEY, provider="zhipu",
    )

    # ========== 知识库（星火知识库 chatdoc.xfyun.cn）==========
    KB_APP_ID: str = APP_ID
    KB_SECRET: str = API_SECRET  # 知识库使用相同的 secret 做 HMAC 签名
    KB_API_URL: str = "https://chatdoc.xfyun.cn/openapi/v1"
    KB_WS_URL: str = "wss://chatdoc.xfyun.cn/openapi/chat"

    # 模型映射
    MODEL_MAP: dict = field(default_factory=lambda: {})

    def __post_init__(self):
        self.MODEL_MAP = {
            "spark-pro": self.SPARK_PRO,
            "spark-lite": self.SPARK_LITE,
            "spark-x2-flash": self.SPARK_X2_FLASH,
            "spark-max-32k": self.SPARK_MAX_32K,
            "spark-generalv3": self.SPARK_GENERALV3,
            "spark-4.0-ultra": self.SPARK_ULTRA,
            "4.0ultra": self.SPARK_ULTRA,
            "glm-4.7-flash": self.GLM_4_7_FLASH,
            "glm-4.5-flash": self.GLM_4_5_FLASH,
            "glm-4-flash": self.GLM_4_FLASH,
        }
        # 旧名称兼容
        for old_name in ["spark-edu-x1", "spark-base-cn", "spark-math-pro", "spark-code-asst"]:
            self.MODEL_MAP[old_name] = self.SPARK_PRO
        # spark-ultra-32k → spark-max-32k
        self.MODEL_MAP["spark-ultra-32k"] = self.SPARK_MAX_32K

    def get_model(self, name: str):
        return self.MODEL_MAP.get(name.lower())

    def list_models(self) -> list[str]:
        return list(self.MODEL_MAP.keys())

    @property
    def is_configured(self) -> bool:
        return bool(self.APP_ID and self.API_KEY and self.API_SECRET)


settings = Settings()
settings.__post_init__()

if settings.is_configured:
    logger.info(f"API 已配置: APP_ID={settings.APP_ID[:4]}..., 可用模型={len(settings.MODEL_MAP)}个")
else:
    logger.warning("API 未配置！")
