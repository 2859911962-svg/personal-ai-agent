#!/bin/bash
# =============================================
#  个人 AI 智能体 — 本地启动脚本
# =============================================

set -e

echo "========================================="
echo "  🧠 个人 AI 智能体"
echo "========================================="
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 需要 Python 3.9+"
    exit 1
fi

# 安装依赖
echo "📦 安装依赖..."
pip3 install -r requirements.txt -q

# 创建数据目录
mkdir -p data

# 加载 .env
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# 启动
echo ""
echo "🚀 启动中..."
echo "   👉 本地访问: http://localhost:8501"
echo "   👉 手机访问: http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo '你的IP'):8501"
echo ""

streamlit run app.py --server.port 8501 --server.address 0.0.0.0
