# API 入口

这里放面向后端服务的薄入口。

当前 `apps/api/` 不直接承载产品逻辑，只转发到
`src/isotope/apps/api.py`。

- `ApiApp`：ASGI（Python Web 服务通用接口）兼容应用边界。
- `create_api_app(...)`：创建后端应用，内部复用 `interfaces/http.py`。
- `isotope-api routes --root <dir>`：列出当前支持的 API 路由。

当前不是完整 FastAPI 服务，也不监听端口。
后续若接入 FastAPI / Uvicorn，应继续让业务逻辑留在 `src/isotope/`
的功能层里。
