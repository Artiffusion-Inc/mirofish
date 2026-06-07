# 贡献指南

感谢你对 MiroFish-Local 的关注！我们欢迎任何形式的贡献。

## 如何提交 Issue

- **Bug 报告**：使用 [Bug Report](https://github.com/tt-a1i/MiroFish-local/issues/new?template=bug_report.yml) 模板
- **功能建议**：使用 [Feature Request](https://github.com/tt-a1i/MiroFish-local/issues/new?template=feature_request.yml) 模板

## 如何提交 PR

1. **Fork** 本仓库
2. 创建特性分支：`git checkout -b feat/your-feature`
3. 提交变更：`git commit -m "feat: add your feature"`
4. 推送分支：`git push origin feat/your-feature`
5. 创建 **Pull Request**

## 开发环境搭建

请参考 [README.md](./README.md) 的「快速开始」章节配置开发环境。

## 代码规范

| 语言 | 规范 | 工具 |
|------|------|------|
| Python | PEP 8 | `ruff check .` |
| JavaScript | ESLint | `npm run lint` |

## Commit Message 规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat: add graphiti backend support` |
| `fix` | Bug 修复 | `fix: resolve neo4j connection timeout` |
| `docs` | 文档更新 | `docs: update README` |
| `refactor` | 重构 | `refactor: extract graph storage interface` |
| `test` | 测试 | `test: add backend unit tests` |
| `chore` | 构建/工具 | `chore: update dependencies` |

## 许可证

提交贡献即表示你同意将代码以本项目相同的许可证（AGPL-3.0）发布。
