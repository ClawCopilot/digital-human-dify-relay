import json
import os
import redis
import uuid
import requests
from fastapi.responses import StreamingResponse
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """健康检查端点，配合 docker-compose healthcheck 使用"""
    return {"status": "ok"}


# 连接到Redis服务器（默认端口是6379）
redis_instance = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=0,
)
mock_time_created = 20230512084843
mock_id1 = "131424542124"
mock_id2 = "1231414141541252525"
mock_user = "abc-123"
dify_url = os.getenv("DIFY_URL", "")
dify_api_key = "Bearer " + os.getenv("DIFY_API_KEY", "")


class Message(BaseModel):
    content: str


class Resquest_Body(BaseModel):
    messages: List[Message] = []
    app_id: str
    user: str
    session_id: str
    is_stream: bool


# 对接dify，非流式传输
def request_dify_api(question, request, conversation_id):
    # 目标URL（自动拼接 /chat-messages）
    url = dify_url.rstrip("/") + "/chat-messages"
    headers_json = {
        'Content-Type': 'application/json',
        'Authorization': dify_api_key
    }
    # 请求的数据
    data = {
        "inputs": {},
        "query": question,
        "response_mode": "blocking",
        "user": mock_user
    }

    # 发送POST请求
    response = requests.post(url, data=json.dumps(data), headers=headers_json)
    resp_data = response.json()
    return resp_data["answer"]


# 对接dify，流式传输
async def generate_streaming_messages(question, request, session_id, conversation_id):
    url = dify_url.rstrip("/") + "/chat-messages"
    headers_json = {
        'Content-Type': 'application/json',
        'Authorization': dify_api_key
    }

    # 请求的数据
    request_data = {
        "inputs": {},
        "query": question,
        "conversation_id": conversation_id,
        "response_mode": "streaming",
        "user": mock_user
    }
    r = requests.post(url, json=request_data, headers=headers_json, verify=False, stream=True)
    if r.status_code != 200:
        raise Exception(r.text)

    data = ""

    # 在这里，我们使用了 iter_lines 方法来逐行读取响应体
    for line in r.iter_lines():
        if await request.is_disconnected():
            # 客户端已主动断开，中止流式输出，避免不必要的问题，打印报错信息方便定位
            print("# 客户端已主动断开，中止流式输出")
            break

        # 将每一行解码为字符串
        line = line.decode('utf-8').strip()

        # 接下来我们要处理三种不同的情况：
        #   1. 如果当前行是空行，则表明前一个数据块已接收完毕（即前文提到的，通过两个换行符结束数据块传输），我们可以对该数据块进行反序列化，并打印出对应的 content 内容；
        #   2. 如果当前行为非空行，且以 data: 开头，则表明这是一个数据块传输的开始，我们去除 data: 前缀后，首先判断是否是结束符 [DONE]，如果不是，将数据内容保存到 data 变量；
        #   3. 如果当前行为非空行，但不以 data: 开头，则表明当前行仍然归属上一个正在传输的数据块，我们将当前行的内容追加到 data 变量尾部；

        if len(line) == 0:
            if data:
                try:
                    chunk = json.loads(data)
                except:
                    continue

                if chunk["event"] != "message":
                    continue
                # 如果redis里未缓存该session_id，则使用reids关联session_id和conversation_id，保证后续实现多轮对话
                if not redis_instance.exists(session_id):
                    conversiation_id = str(chunk["conversation_id"])
                    redis_instance.set(session_id, conversiation_id)

                    # 设置redis中key（session_id）的超时时间，一天换算86400s
                    redis_instance.expire(session_id, 86400)
                content = chunk["answer"]
                new_data = {
                    "id": mock_id2,
                    "created": mock_time_created,
                    "choices": [{
                        "message": {
                            "content": content
                        }
                    }]
                }
                yield f"data: {json.dumps(new_data, ensure_ascii=False)}\n\n"

                data = ""  # 重置 data
        elif line.startswith("data: "):
            data = line.lstrip("data: ")

            # 当数据块内容为 [DONE] 时，则表明所有数据块已发送完毕，可断开网络连接
            if data == "[DONE]":
                break
        else:
            # 仍然在追加内容时，为其添加一个换行符
            data = data + "\n" + line

            # 发送结束标记
    yield "data: [DONE]\n\n"


@app.post("/digital-human")
async def digital_human(body: Resquest_Body, request: Request):
    question = body.messages[0].content
    session_id = body.session_id
    conversation_id = ""

    #  如果redis_instance里有缓存session_id，则说明为多轮对话，获取对应的dify中的多轮对话关键参数conversation_id
    if redis_instance.exists(session_id):
        # decode()用于将bytes转换为str，因为redis_instance存储的是bytes类型的数据。
        conversation_id = redis_instance.get(session_id).decode("utf-8")

    #  选择流式传输
    if body.is_stream:
        return StreamingResponse(
            generate_streaming_messages(question, request, session_id, conversation_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    #  选择非流式传输
    answer = request_dify_api(question, request, conversation_id)
    choices = [{
        "index": 0,
        "message": {
            "content": answer
        }
    }]
    return {
        "id": mock_id1,
        "created": mock_time_created,
        "choices": choices
    }


# 启动应用
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
