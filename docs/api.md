# HTTP 服务与部署

## FastAPI 服务

```bash
pip install ".[server]"
uvicorn thermolit.api:app --port 8000
```

| 端点 | 说明 |
|------|------|
| `POST /survey` | 提交调研任务,返回 `{job_id}`;后台线程执行 |
| `GET /jobs/{id}` | 任务状态与产物(报告/审计表/假说/实验方案/DOI 核验/metrics) |
| `GET /health` | 存活探针 |

```bash
curl -X POST localhost:8000/survey -H "content-type: application/json" \
     -d '{"query": "PbTe thermoelectric zT decoupling", "top_k": 3, "check_dois": true}'
curl localhost:8000/jobs/<job_id>
```

## Gradio 演示

```bash
pip install ".[ui]"
python -m thermolit.ui        # 浏览器交互:输入查询 → 报告/审计表/假说三个面板
```

## Docker

```bash
docker build -t thermolit .
docker run -p 8000:8000 --env-file .env thermolit
```

镜像基于 `python:3.11-slim`,安装 `.[server,export,checkpoint]`,以非 root 用户运行。

## 断点续跑

```bash
thermolit --checkpoint run.db --query "..."
```

SqliteSaver 落盘每个节点状态;同 query+profile 派生同一 thread_id,中断后重跑同一命令即从断点恢复。
