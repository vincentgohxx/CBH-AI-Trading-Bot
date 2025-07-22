# 使用官方的、轻量级的Python 3.10镜像作为基础
FROM python:3.10-slim

# 在容器内设置工作目录
WORKDIR /app

# 将我们的“购物清单”复制进去
COPY requirements.txt .

# 安装所有我们需要的Python库
RUN pip install --no-cache-dir -r requirements.txt

# 将我们机器人的所有代码复制进去
COPY . .

# 设置启动命令，告诉容器如何运行我们的机器人
# 注意：Supabase Functions with Docker 需要一个Web服务器
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "index:handler_asgi"]
