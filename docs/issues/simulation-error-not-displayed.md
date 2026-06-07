# Issue: 模拟失败时前端未显示错误信息 [已修复]

**状态**: 已修复
**修复日期**: 2026-01-05
**修复文件**: `frontend/src/components/Step3Simulation.vue`

## 问题描述

当后端模拟运行失败时，错误信息只出现在后端日志中，前端界面没有任何错误提示，用户无法感知到模拟已经失败。

## 复现步骤

1. 启动前后端服务
2. 创建项目并上传文档
3. 构建 GraphRAG（成功）
4. 点击"开始模拟"
5. 模拟因缺少依赖而失败

## 实际行为

**后端日志显示错误：**
```
错误: 缺少依赖 No module named 'camel'
请先安装: pip install oasis-ai camel-ai
```

**前端表现：**
- 没有任何错误提示
- 界面可能显示"模拟中"状态但不更新
- 用户无法得知模拟已失败

## 期望行为

- 前端应显示明确的错误提示（如 Toast/Modal）
- 错误信息应包含具体原因
- 用户应能看到"安装依赖"的建议

## 技术分析

### 可能的原因

1. **API 响应未正确返回错误**
   - 后端可能只打印日志但返回了空响应或非标准错误格式

2. **前端未处理错误响应**
   - API 调用的 catch 块可能为空或未实现

3. **WebSocket/SSE 连接问题**
   - 如果使用实时通信，错误事件可能未被监听

### 需要检查的文件

| 位置 | 文件 | 检查内容 |
|------|------|----------|
| 后端 | `app/routes/*.py` | API 错误响应格式 |
| 后端 | `app/services/simulation*.py` | 异常处理逻辑 |
| 前端 | `src/api/*.ts` | API 调用错误处理 |
| 前端 | `src/components/*Simulation*.tsx` | 错误状态展示 |

## 建议修复方案

### 方案 A：统一错误响应格式

```python
# 后端 API 返回标准错误格式
@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({
        "success": False,
        "error": {
            "code": "SIMULATION_FAILED",
            "message": str(e),
            "suggestion": get_suggestion(e)
        }
    }), 500
```

### 方案 B：前端全局错误处理

```typescript
// 前端 axios 拦截器
api.interceptors.response.use(
  response => response,
  error => {
    const message = error.response?.data?.error?.message || '未知错误';
    toast.error(message);
    return Promise.reject(error);
  }
);
```

## 相关背景

此问题在测试 Graphiti 本地化方案时发现。由于 `camel-ai` 与 `graphiti-core` 存在 neo4j 版本冲突：
- `camel-ai` 需要 `neo4j==5.23.0`
- `graphiti-core` 需要 `neo4j>=5.26.0`

导致模拟功能无法正常运行，但该错误未能传达给用户。

## 优先级

**中等** - 影响用户体验，但不影响核心功能

## 标签

- `bug`
- `frontend`
- `error-handling`
- `ux`

---

## 修复详情

### 根因

`Step3Simulation.vue` 的 `fetchRunStatus()` 函数只检查了 `completed` 和 `stopped` 状态，**完全忽略了 `failed` 状态**：

```javascript
// 原代码 (第 512 行)
const isCompleted = data.runner_status === 'completed' || data.runner_status === 'stopped'
// 缺少对 runner_status === 'failed' 的处理
```

### 修复方案

在 `fetchRunStatus()` 中添加对 `failed` 状态的检测（第 511-519 行）：

```javascript
// 检测模拟是否失败
if (data.runner_status === 'failed') {
  const errorMsg = data.error || '模拟运行失败'
  addLog(`✗ 模拟失败: ${errorMsg}`)
  phase.value = 2  // 进入完成阶段（允许查看日志/重试）
  stopPolling()
  emit('update-status', 'error')
  return
}
```

### 修复效果

- 前端日志面板显示错误信息：`✗ 模拟失败: 进程退出码: 1, 错误: ...No module named 'camel'...`
- 状态指示器变为 error 状态（红色）
- 用户可以清晰看到模拟失败的原因
