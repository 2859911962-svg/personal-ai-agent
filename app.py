"""
个人 AI 智能体 — 移动端 Web 界面 v2
- 响应式设计，手机/平板/电脑全适配
- 账号密码登录，独立记忆和人设
- 仿聊天 App 体验
"""

import streamlit as st
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from agent import PersonalAgent, register_user, verify_user, DEFAULT_PERSONA

st.set_page_config(
    page_title="我的AI伙伴",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ============================================================
# 移动端样式
# ============================================================

st.markdown("""
<style>
    /* 全局 */
    .stApp {
        background: #0a0e14;
        max-width: 600px;
        margin: 0 auto;
    }
    .main .block-container {
        padding: 0.5rem 0.8rem !important;
        max-width: 600px;
    }

    /* 隐藏 Streamlit 默认元素 */
    #MainMenu, footer, .stDeployButton, [data-testid="stSidebar"] {
        display: none !important;
    }
    header[data-testid="stHeader"] {
        background: transparent !important;
    }

    /* 顶栏 */
    .topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px 4px;
        border-bottom: 1px solid #1a2230;
        position: sticky;
        top: 0;
        background: #0a0e14;
        z-index: 100;
        margin-bottom: 4px;
    }
    .topbar .title {
        font-size: 17px;
        font-weight: 700;
        color: #e0e0e0;
    }
    .topbar .subtitle {
        font-size: 12px;
        color: #5c7a8a;
    }

    /* 聊天气泡 */
    .chat-container {
        padding: 0 4px;
        margin-bottom: 80px;
    }
    .msg-row {
        display: flex;
        margin-bottom: 14px;
        animation: slideUp 0.25s ease;
    }
    @keyframes slideUp {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .msg-row.user {
        justify-content: flex-end;
    }
    .msg-row.assistant {
        justify-content: flex-start;
    }
    .bubble {
        max-width: 82%;
        padding: 10px 14px;
        border-radius: 18px;
        font-size: 15px;
        line-height: 1.6;
        word-break: break-word;
    }
    .bubble.user {
        background: linear-gradient(135deg, #1a6bff, #4a90ff);
        color: #fff;
        border-bottom-right-radius: 6px;
    }
    .bubble.assistant {
        background: #151d28;
        color: #d0d8e0;
        border: 1px solid #1e2a3a;
        border-bottom-left-radius: 6px;
    }
    .bubble .avatar {
        font-size: 13px;
        margin-bottom: 4px;
        opacity: 0.6;
    }
    .bubble.user .avatar { text-align: right; }
    .bubble.assistant .avatar { text-align: left; }

    /* 底部输入栏 */
    .input-bar {
        position: fixed;
        bottom: 0;
        left: 50%;
        transform: translateX(-50%);
        width: 100%;
        max-width: 600px;
        padding: 8px 12px 12px;
        background: #0a0e14;
        border-top: 1px solid #1a2230;
    }
    .stChatInput > div {
        background: #151d28 !important;
        border: 1px solid #1e2a3a !important;
        border-radius: 24px !important;
        padding: 4px 8px !important;
    }
    .stChatInput input {
        background: transparent !important;
        border: none !important;
        color: #e0e0e0 !important;
        font-size: 15px !important;
    }
    .stChatInput input::placeholder {
        color: #3a4a5a !important;
    }

    /* 登录页 */
    .login-box {
        max-width: 340px;
        margin: 80px auto 0;
        padding: 32px 24px;
        background: #111822;
        border-radius: 20px;
        border: 1px solid #1e2a3a;
        text-align: center;
    }
    .login-box h2 {
        color: #e0e0e0;
        font-size: 22px;
        margin-bottom: 6px;
    }
    .login-box .sub {
        color: #5c7a8a;
        font-size: 14px;
        margin-bottom: 24px;
    }
    .stTextInput > div > div > input {
        background: #151d28 !important;
        border: 1px solid #1e2a3a !important;
        border-radius: 12px !important;
        color: #e0e0e0 !important;
        padding: 10px 14px !important;
    }
    .stButton > button {
        width: 100% !important;
        border-radius: 12px !important;
        background: linear-gradient(135deg, #1a6bff, #4a90ff) !important;
        color: white !important;
        border: none !important;
        padding: 10px !important;
        font-weight: 600 !important;
        font-size: 15px !important;
    }
    .stButton > button:hover {
        opacity: 0.9;
    }

    /* 设置面板 */
    .settings-section {
        background: #111822;
        border-radius: 16px;
        padding: 16px;
        margin: 8px 0;
        border: 1px solid #1e2a3a;
    }
    .settings-section h4 {
        color: #4a90ff;
        font-size: 15px;
        margin-bottom: 10px;
    }
    .settings-section label {
        color: #8899aa !important;
        font-size: 13px !important;
    }

    /* 记忆卡片 */
    .mem-card {
        background: #151d28;
        border-radius: 12px;
        padding: 10px 12px;
        margin: 4px 0;
        font-size: 13px;
        color: #b0c0d0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .mem-card .cat-badge {
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 10px;
        background: #1e2a3a;
        color: #6a8a9a;
        margin-right: 8px;
        flex-shrink: 0;
    }

    /* Toast */
    .toast {
        position: fixed;
        top: 16px;
        left: 50%;
        transform: translateX(-50%);
        background: #1a6bff;
        color: white;
        padding: 10px 20px;
        border-radius: 20px;
        font-size: 14px;
        z-index: 999;
        animation: fadeInOut 2s ease;
    }
    @keyframes fadeInOut {
        0% { opacity: 0; top: 0; }
        15% { opacity: 1; top: 16px; }
        85% { opacity: 1; top: 16px; }
        100% { opacity: 0; top: 0; }
    }

    /* 响应式 */
    @media (max-width: 480px) {
        .bubble { max-width: 88%; font-size: 15px; }
        .login-box { margin-top: 40px; padding: 24px 16px; }
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# Session State
# ============================================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "messages" not in st.session_state:
    st.session_state.messages = []
if "show_settings" not in st.session_state:
    st.session_state.show_settings = False
if "show_memories" not in st.session_state:
    st.session_state.show_memories = False


# ============================================================
# 辅助函数
# ============================================================

def get_agent():
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    return PersonalAgent(st.session_state.username, api_key)


def add_message(role: str, content: str):
    st.session_state.messages.append({
        "role": role,
        "content": content,
        "time": time.strftime("%H:%M")
    })


# ============================================================
# 登录页面
# ============================================================

if not st.session_state.logged_in:
    st.markdown("""
    <div class="login-box">
        <h2>🧠 我的AI伙伴</h2>
        <p class="sub">专属智能体 · 永远记得你</p>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["登录", "注册"])

    with tab1:
        login_user = st.text_input("用户名", key="login_user", placeholder="输入用户名")
        login_pass = st.text_input("密码", type="password", key="login_pass", placeholder="输入密码")
        if st.button("登录", key="btn_login"):
            if not login_user or not login_pass:
                st.error("请填写用户名和密码")
            elif verify_user(login_user, login_pass):
                st.session_state.logged_in = True
                st.session_state.username = login_user
                agent = PersonalAgent(login_user)
                greeting = agent.persona.get("greeting", f"嗨！我是{agent.persona['name']}，你的专属伙伴 👋")
                st.session_state.messages = []
                add_message("assistant", greeting)
                st.rerun()
            else:
                st.error("用户名或密码错误")

    with tab2:
        reg_user = st.text_input("用户名", key="reg_user", placeholder="起个名字")
        reg_pass = st.text_input("密码", type="password", key="reg_pass", placeholder="设置密码（6位以上）")
        reg_pass2 = st.text_input("确认密码", type="password", key="reg_pass2", placeholder="再输一遍")
        if st.button("注册", key="btn_reg"):
            if not reg_user or not reg_pass:
                st.error("请填写完整")
            elif len(reg_pass) < 6:
                st.error("密码至少6位")
            elif reg_pass != reg_pass2:
                st.error("两次密码不一致")
            elif len(reg_user) < 2:
                st.error("用户名至少2个字符")
            elif register_user(reg_user, reg_pass):
                st.success("注册成功！请切换到登录")
            else:
                st.error("用户名已存在")

    st.stop()


# ============================================================
# 主界面
# ============================================================

agent = get_agent()
p = agent.persona

# === 设置弹窗 ===
if st.session_state.show_settings:
    st.markdown('<div class="settings-section">', unsafe_allow_html=True)
    st.markdown(f"<h4>🎭 人设设置</h4>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        new_name = st.text_input("名字", value=p["name"], key="set_name")
        new_nickname = st.text_input("昵称", value=p["nickname"], key="set_nick")
        new_personality = st.text_input("性格", value=p["personality"], key="set_pers")
    with col2:
        new_user_name = st.text_input("怎么称呼你", value=p["user_name"], key="set_uname")
        new_domains = st.text_input("擅长领域", value=", ".join(p["knowledge_domains"]), key="set_doms")

    new_style = st.text_area("说话风格", value=p["speaking_style"], key="set_style", height=68)

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("💾 保存", use_container_width=True):
            agent.update_persona(
                name=new_name, nickname=new_nickname,
                personality=new_personality, speaking_style=new_style,
                knowledge_domains=new_domains, user_name=new_user_name
            )
            st.session_state.show_settings = False
            st.rerun()
    with c2:
        if st.button("↩ 返回", use_container_width=True):
            st.session_state.show_settings = False
            st.rerun()
    with c3:
        if st.button("🚪 退出", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.messages = []
            st.session_state.show_settings = False
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()


# === 记忆查看 ===
if st.session_state.show_memories:
    st.markdown('<div class="settings-section">', unsafe_allow_html=True)
    st.markdown(f"<h4>💾 长期记忆 ({agent.memory.count()}条)</h4>", unsafe_allow_html=True)

    memories = agent.memory.list_all(50)
    if memories:
        for mem in memories:
            cat = mem.get("category", "general")
            cat_emoji = {"personal": "👤", "work": "💼", "idea": "💡", "knowledge": "📚"}.get(cat, "📌")
            st.markdown(f"""
            <div class="mem-card">
                <span><span class="cat-badge">{cat_emoji} {cat}</span>{mem['content'][:80]}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.caption("还没有长期记忆，聊天时会自动记录")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("↩ 返回聊天", use_container_width=True):
            st.session_state.show_memories = False
            st.rerun()
    with c2:
        if st.button("🧹 清空记忆", use_container_width=True):
            for m in agent.memory.list_all(500):
                agent.memory.forget(m["id"])
            st.session_state.show_memories = False
            st.rerun()
    with c3:
        if st.button("🔄 清空对话", use_container_width=True):
            agent.history.clear()
            st.session_state.messages = []
            add_message("assistant", agent.persona.get("greeting", "嘿！"))
            st.session_state.show_memories = False
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()


# === 顶栏 ===
st.markdown(f"""
<div class="topbar">
    <div>
        <div class="title">{p['name']}</div>
        <div class="subtitle">{p['personality']} · {p['user_name']}的伙伴</div>
    </div>
    <div style="display:flex;gap:6px;">
        <span style="cursor:pointer;font-size:20px;" id="btn_mem">💾</span>
        <span style="cursor:pointer;font-size:20px;" id="btn_set">⚙️</span>
    </div>
</div>
""", unsafe_allow_html=True)

# 顶栏按钮
col_top1, col_top2 = st.columns([1, 8])
with col_top1:
    if st.button("💾", key="btn_memories", help="查看记忆"):
        st.session_state.show_memories = True
        st.rerun()
with col_top2:
    if st.button("⚙️", key="btn_settings", help="设置"):
        st.session_state.show_settings = True
        st.rerun()


# === 聊天区域 ===
st.markdown('<div class="chat-container">', unsafe_allow_html=True)

for msg in st.session_state.messages:
    role = msg["role"]
    content = msg["content"]
    avatar_label = p["user_name"] if role == "user" else p["name"]
    st.markdown(f"""
    <div class="msg-row {role}">
        <div class="bubble {role}">
            <div class="avatar">{avatar_label}</div>
            {content}
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)


# === 底部输入 ===
st.markdown('<div class="input-bar">', unsafe_allow_html=True)

if prompt := st.chat_input(f"跟 {p['name']} 说点什么..."):

    add_message("user", prompt)

    with st.spinner(""):
        if not os.getenv("DEEPSEEK_API_KEY", ""):
            response = "⚠️ 管理员还没配置 API Key，请联系部署者设置 DEEPSEEK_API_KEY"
        else:
            response = agent.chat(prompt)

    add_message("assistant", response)
    st.rerun()

st.markdown('</div>', unsafe_allow_html=True)
