import logging

logger = logging.getLogger(__name__)

print("找到 3 篇文档")
logger.info("search completed", extra={"result_count": 3})
