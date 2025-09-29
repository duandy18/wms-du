# WMS-DU 开发约定 v0.1

本约定覆盖代码与文档的最小规则，目标是降低协作摩擦、避免无意义的差异。后续可根据需要迭代。

---

## 1. 语言
- **代码层**：变量名、函数名、类名、注释一律英文。  
- **文档层**：设计文档、Canvas、README 可用中文，但推荐半角标点。  
- **提交信息**：英文为主，可在正文附中文说明。

---

## 2. 符号
- 代码和配置文件中统一使用 **半角**（英文）标点。  
- 中文文档可用中文标点，但需保证与 Markdown、YAML、JSON 兼容。  

---

## 3. 命名
- **Python**  
  - 变量/函数：`snake_case`  
  - 类名：`PascalCase`  
  - 常量：`UPPER_CASE`
- **数据库**  
  - 表/字段名：`snake_case`，全部小写  
  - 避免拼音或中英文混杂  

---

## 4. 提交信息（Git）
遵循 [Conventional Commits](https://www.conventionalcommits.org/)：
- `feat: add supplier model`
- `fix: correct PO status transition`
- `chore: update CI config`
- `docs: add RBAC conventions`

---

## 5. 测试
- 测试函数名与断言消息统一英文。  
- 每个新功能必须附带对应测试，确保覆盖率不下降。  

---

## 6. 文档与注释
- 简要注释写在代码行上方，避免堆砌。  
- 复杂业务逻辑（如采购单状态流转）写在 `docs/` 下的独立文档，并在代码中引用链接。  

---

## 7. 例外说明
如确需使用中文（例如：法定字段名、外部接口返回值），必须在注释或文档里标明理由。  

---

> 本约定版本：v0.1（2025-09）  
> 制定阶段：RBAC-lite 起步期  
> 后续可由团队共同更新。
