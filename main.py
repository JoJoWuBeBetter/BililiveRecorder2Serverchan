from fastapi import FastAPI
from api.routers import webhook, cos_api, task_api  # 导入 webhook 路由器
from config import logger  # 导入 config 中的 logger，确保日志配置一致
from database import create_db_and_tables
from api.exception_handlers import setup_exception_handlers

# 在应用启动时，同步地创建数据库和所有表
# 这行代码将读取所有继承自 Base 的模型，并在数据库中创建对应的表
print("Attempting to create database tables...")
create_db_and_tables()
print("Database tables creation process finished.")

app = FastAPI(
    title="录播姬 Webhook 转 ServerChan",
    description="接收录播姬 Webhook 请求，并将其内容格式化后转发至 ServerChan。",
    version="2.2.4"
)

# 设置全局异常处理器
setup_exception_handlers(app)

# 包含 Webhook 路由
app.include_router(webhook.router)
app.include_router(cos_api.router)
app.include_router(task_api.router)


@app.get("/")
async def root():
    """根路径，用于简单的健康检查或欢迎信息"""
    logger.info("Root endpoint accessed.")
    return {"message": "Welcome to Bililive Webhook to ServerChan Forwarder!"}


# 可以添加一个 __main__ 块以便直接运行，但在生产环境中通常使用 gunicorn 或 uvicorn 命令启动
if __name__ == "__main__":
    import uvicorn

    # 确保在启动前，环境变量 SERVERCHAN_SEND_KEY 已经设置
    logger.info("Starting FastAPI application...")
    uvicorn.run(app, host="0.0.0.0", port=18000)
