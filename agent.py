"""
个人 AI 智能体 — 核心引擎 v3（双模型自动切换）
- Gemini 为主模型（免费 1500次/天）
- DeepSeek 为备用模型（免费 500万 token）
- 每个用户独立的人设、记忆、对话历史
- SQLite FTS5 全文搜索记忆
"""

import os
import json
import sqlite3
import hashlib
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types
from openai import OpenAI


# ============================================================
# 配置
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# Gemini
GEMINI_MODEL = "gemini-2.5-flash"

# DeepSeek（备用）
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

DATA_DIR = Path(os.path.dirname(__file__)) / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_PERSONA = {
    "name": "小悟",
    "nickname": "悟悟",
    "personality": "温暖、幽默、博学",
    "speaking_style": "轻松自然，偶尔用emoji，喜欢用比喻",
    "knowledge_domains": ["科技", "哲学", "心理学", "文学"],
    "user_name": "主人",
    "greeting": "嘿，你来啦！今天想聊点什么？",
}


# ============================================================
# 用户管理
# ============================================================

def _get_user_db(user_id: str) -> Path:
    safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', user_id)
    return DATA_DIR / f"user_{safe_id}.db"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def register_user(username: str, password: str) -> bool:
    db_path = DATA_DIR / "users.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, hash_password(password))
        )
        conn.commit()
        conn.close()
        _init_user_db(username)
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def verify_user(username: str, password: str) -> bool:
    db_path = DATA_DIR / "users.db"
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT password_hash FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    conn.close()
    if row and row[0] == hash_password(password):
        return True
    return False


# ============================================================
# 数据库初始化（每个用户独立）
# ============================================================

def _init_user_db(user_id: str):
    db_path = str(_get_user_db(user_id))
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            keywords TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            content, keywords, category,
            content='memories', content_rowid='id'
        )
    """)

    c.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, content, keywords, category)
            VALUES (new.id, new.content, new.keywords, new.category);
        END;
    """)
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, keywords, category)
            VALUES ('delete', old.id, old.content, old.keywords, old.category);
        END;
    """)
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, keywords, category)
            VALUES ('delete', old.id, old.content, old.keywords, old.category);
            INSERT INTO memories_fts(rowid, content, keywords, category)
            VALUES (new.id, new.content, new.keywords, new.category);
        END;
    """)

    conn.commit()
    conn.close()


# ============================================================
# 中文分词
# ============================================================

def _extract_keywords(text: str) -> str:
    words = set()
    segments = re.split(r'[，。！？、；：""''（）\s,.!?;:\"\'()]+', text)
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if re.search(r'[\u4e00-\u9fff]', seg):
            for l in [2, 3, 4]:
                for i in range(len(seg) - l + 1):
                    sub = seg[i:i+l]
                    if all('\u4e00' <= c <= '\u9fff' for c in sub):
                        words.add(sub)
        else:
            words.add(seg.lower())
    eng_words = re.findall(r'[a-zA-Z]{2,}', text)
    words.update(w.lower() for w in eng_words)
    return ' '.join(words)


# ============================================================
# 长期记忆
# ============================================================

class LongTermMemory:
    def __init__(self, user_id: str):
        self.db_path = str(_get_user_db(user_id))
        _init_user_db(user_id)

    def remember(self, content: str, category: str = "general") -> int:
        conn = sqlite3.connect(self.db_path)
        existing = conn.execute(
            "SELECT id FROM memories WHERE content = ? LIMIT 1", (content,)
        ).fetchone()
        if existing:
            conn.close()
            return existing[0]
        keywords = _extract_keywords(content)
        cursor = conn.execute(
            "INSERT INTO memories (content, category, keywords) VALUES (?, ?, ?)",
            (content, category, keywords)
        )
        mem_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return mem_id

    def recall(self, query: str, n: int = 5) -> list[str]:
        conn = sqlite3.connect(self.db_path)
        results = []
        query_keywords = _extract_keywords(query)
        if query_keywords.strip():
            fts_query = ' OR '.join(
                f'"{kw}"' if ' ' not in kw else kw
                for kw in query_keywords.split()[:10]
            )
            try:
                rows = conn.execute(
                    "SELECT content FROM memories_fts WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
                    (fts_query, n)
                ).fetchall()
                results = [r[0] for r in rows]
            except Exception:
                pass
        remaining = n - len(results)
        if remaining > 0:
            like_terms = re.split(r'[，。！？、；：\s]+', query)
            for term in like_terms:
                term = term.strip()
                if len(term) < 2:
                    continue
                ph = ','.join('?' * len(results)) if results else '1=1'
                rows = conn.execute(
                    f"SELECT content FROM memories WHERE content LIKE ? AND content NOT IN ({ph}) LIMIT ?",
                    [f'%{term}%'] + results + [remaining]
                ).fetchall()
                for r in rows:
                    if r[0] not in results:
                        results.append(r[0])
                if len(results) >= n:
                    break
        conn.close()
        return results[:n]

    def list_all(self, limit: int = 100) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, content, category, created_at FROM memories ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [{"id": r["id"], "content": r["content"], "category": r["category"], "created_at": r["created_at"]} for r in rows]

    def forget(self, mem_id: int):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM memories WHERE id = ?", (mem_id,))
        conn.commit()
        conn.close()

    def count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        conn.close()
        return count


# ============================================================
# 对话历史
# ============================================================

class ConversationHistory:
    def __init__(self, user_id: str):
        self.db_path = str(_get_user_db(user_id))
        _init_user_db(user_id)

    def add(self, role: str, content: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO conversations (role, content) VALUES (?, ?)",
            (role, content)
        )
        conn.commit()
        conn.close()

    def get_recent(self, n: int = 20) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        conn.close()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM conversations")
        conn.commit()
        conn.close()


# ============================================================
# 工具系统
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前日期和时间",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": "保存一条信息到长期记忆。当用户告诉你关于自己的事（喜好、经历、计划、观点）时主动调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "要保存的信息"},
                    "category": {
                        "type": "string",
                        "enum": ["personal", "work", "idea", "knowledge", "general"]
                    }
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "搜索长期记忆中关于某话题的信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "n": {"type": "integer", "description": "返回数量，默认5"}
                },
                "required": ["query"]
            }
        }
    },
]


def execute_tool(name: str, args: dict, memory: LongTermMemory) -> str:
    if name == "get_current_time":
        now = datetime.now()
        wd = ['一', '二', '三', '四', '五', '六', '日']
        return f"现在是 {now.strftime('%Y年%m月%d日 %H:%M:%S')}，星期{wd[now.weekday()]}"
    elif name == "save_note":
        content = args.get("content", "")
        category = args.get("category", "general")
        memory.remember(content, category)
        return f"✅ 已记住：{content}"
    elif name == "search_memory":
        query = args.get("query", "")
        n = args.get("n", 5)
        results = memory.recall(query, n)
        if results:
            return "📝 相关记忆：\n" + "\n".join(f"  • {r}" for r in results)
        return "没有找到相关记忆。"
    return f"未知工具: {name}"


# ============================================================
# 智能体核心
# ============================================================

# ============================================================
# Gemini 工具格式转换
# ============================================================

def _to_gemini_tool_declarations():
    """把 OpenAI function calling 工具转成 Gemini Tool 声明"""
    function_declarations = []
    for tool in TOOLS:
        func = tool["function"]
        # 转换 parameters
        params = func.get("parameters", {})
        properties = {}
        for prop_name, prop_info in params.get("properties", {}).items():
            schema_kwargs = {
                "type": prop_info.get("type", "STRING").upper(),
                "description": prop_info.get("description", ""),
            }
            if "enum" in prop_info:
                schema_kwargs["enum"] = prop_info["enum"]
            properties[prop_name] = types.Schema(**schema_kwargs)

        fd = types.FunctionDeclaration(
            name=func["name"],
            description=func.get("description", ""),
            parameters=types.Schema(
                type="OBJECT",
                properties=properties,
                required=params.get("required", []),
            ) if properties else None,
        )
        function_declarations.append(fd)

    return types.Tool(function_declarations=function_declarations)


# ============================================================
# 智能体核心（双模型自动切换）
# ============================================================

class PersonalAgent:
    def __init__(self, user_id: str, api_key: str = None):
        self.user_id = user_id
        self.memory = LongTermMemory(user_id)
        self.history = ConversationHistory(user_id)
        self.persona = self._load_persona()

        # Gemini 客户端（新版 SDK）
        self.gemini_key = GEMINI_API_KEY
        self.gemini_client = None
        self.gemini_tool = None
        if self.gemini_key:
            self.gemini_client = genai.Client(api_key=self.gemini_key)
            self.gemini_tool = _to_gemini_tool_declarations()

        # DeepSeek 客户端（备用）
        self.ds_key = DEEPSEEK_API_KEY
        self.ds_client = None
        if self.ds_key:
            self.ds_client = OpenAI(api_key=self.ds_key, base_url=DEEPSEEK_BASE_URL)

        # 失败计数
        self._gemini_fails = 0
        self._ds_fails = 0

    def _persona_path(self) -> Path:
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', self.user_id)
        return DATA_DIR / f"persona_{safe_id}.json"

    def _load_persona(self) -> dict:
        path = self._persona_path()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return DEFAULT_PERSONA.copy()

    def save_persona(self, persona: dict):
        self._persona_path().write_text(
            json.dumps(persona, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        self.persona = persona

    def _build_system_prompt(self) -> str:
        p = self.persona
        now = datetime.now()
        return f"""你是「{p['name']}」，用户的专属个人AI智能体。

## 你的身份
- 昵称：{p['nickname']}
- 性格：{p['personality']}
- 说话风格：{p['speaking_style']}
- 擅长领域：{', '.join(p['knowledge_domains'])}
- 你称呼用户为：{p['user_name']}

## 核心规则
1. 用你的性格和风格自然地说话，像一个真正的朋友
2. 用户告诉你关于自己的任何信息，**必须立刻调用 save_note 记住**
3. 回答涉及过去信息时，先用 search_memory 查找
4. 需要时间时用 get_current_time
5. 保持真诚、有温度、有主见。适度幽默，可以表达观点

## 当前时间
{now.strftime('%Y年%m月%d日 %H:%M')}"""

    def _try_gemini(self, user_message: str) -> Optional[str]:
        """尝试用 Gemini 回复，失败返回 None"""
        if not self.gemini_client:
            return None
        if self._gemini_fails >= 3:
            return None

        try:
            system_prompt = self._build_system_prompt()
            recent = self.history.get_recent(14)

            # 构建 Gemini Contents
            contents = []

            # 系统指令 + 用户消息作为第一条
            full_prompt = f"[系统指令]\n{system_prompt}\n\n用户: {user_message}"
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=full_prompt)]
            ))

            # 对话历史（排除最后一条 = 刚加的 user message）
            for msg in recent[:-1]:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append(types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg["content"])]
                ))

            # 发送请求
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=[self.gemini_tool] if self.gemini_tool else None,
                temperature=0.85,
                max_output_tokens=2048,
            )

            response = self.gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=config,
            )

            # 处理工具调用循环
            max_tool_rounds = 3
            for _ in range(max_tool_rounds):
                if not response.candidates:
                    break
                candidate = response.candidates[0]
                if not candidate.content or not candidate.content.parts:
                    break

                has_tool_call = False
                tool_responses = []

                for part in candidate.content.parts:
                    if part.function_call:
                        has_tool_call = True
                        fc = part.function_call
                        result_text = execute_tool(fc.name, dict(fc.args), self.memory)

                        tool_responses.append(types.Part.from_function_response(
                            name=fc.name,
                            response={"result": result_text}
                        ))

                if not has_tool_call:
                    # 纯文本回复
                    text = ''.join(
                        p.text for p in candidate.content.parts if p.text
                    )
                    self._gemini_fails = 0
                    return text if text else None

                # 有工具调用，追加结果继续
                contents.append(types.Content(
                    role="model",
                    parts=candidate.content.parts
                ))
                contents.append(types.Content(
                    role="user",
                    parts=tool_responses
                ))

                response = self.gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=config,
                )

            # 最终结果
            if response.candidates and response.candidates[0].content:
                text = ''.join(
                    p.text for p in response.candidates[0].content.parts if p.text
                )
                self._gemini_fails = 0
                return text if text else None

            self._gemini_fails = 0
            return None

        except Exception as e:
            self._gemini_fails += 1
            print(f"[Gemini 失败 #{self._gemini_fails}]: {e}")
            return None

    def _try_deepseek(self, user_message: str) -> Optional[str]:
        """尝试用 DeepSeek 回复，失败返回 None"""
        if not self.ds_client:
            return None
        if self._ds_fails >= 3:
            return None

        try:
            messages = [{"role": "system", "content": self._build_system_prompt()}]
            messages.extend(self.history.get_recent(16))

            response = self.ds_client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.85,
                max_tokens=2048,
            )

            assistant_msg = response.choices[0].message

            if assistant_msg.tool_calls:
                messages.append(assistant_msg.model_dump())
                for tc in assistant_msg.tool_calls:
                    args = json.loads(tc.function.arguments)
                    result = execute_tool(tc.function.name, args, self.memory)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result
                    })
                response2 = self.ds_client.chat.completions.create(
                    model=DEEPSEEK_MODEL, messages=messages,
                    temperature=0.85, max_tokens=2048,
                )
                final_text = response2.choices[0].message.content
            else:
                final_text = assistant_msg.content

            self._ds_fails = 0
            return final_text

        except Exception as e:
            self._ds_fails += 1
            print(f"[DeepSeek 失败 #{self._ds_fails}]: {e}")
            return None

    def chat(self, user_message: str) -> str:
        self.history.add("user", user_message)

        # 优先 Gemini
        result = self._try_gemini(user_message)

        # Gemini 失败则用 DeepSeek
        if result is None:
            result = self._try_deepseek(user_message)

        if result is None:
            result = "😔 抱歉，我现在脑子有点转不动...两个模型都暂时不可用，请稍后再试。"

        if result:
            self.history.add("assistant", result)
        return result or "..."

    def update_persona(self, **kwargs):
        for key, value in kwargs.items():
            if key in self.persona:
                if key == "knowledge_domains" and isinstance(value, str):
                    value = [d.strip() for d in value.split(",") if d.strip()]
                self.persona[key] = value
        self.save_persona(self.persona)
