# xiaoxiao-Fetches-Warehouse

按需竞品价格核验仓库。核心原则：**不能验证，就不报价格。**

## 工作方式

1. 用户在 ChatGPT 发“产品/Variant + 官方 URL”。
2. ChatGPT 在本仓库创建标题以 `[SCRAPE]` 开头的 Issue。
3. GitHub Actions 自动启动 Chromium + Playwright。
4. 抓取官方页面、同源商品数据、最终跳转地址、库存与价格。
5. 只有产品/Variant 与价格形成证据闭环，状态才是 `VERIFIED`。
6. Action 自动把结果评论回 Issue；ChatGPT 再读取并整理给用户。

日常运行**不使用 Codex，不调用 OpenAI API**。

## 永远禁止

- Google/Bing 摘要补官网价
- 第三方经销商价格补官网价
- 历史价补当前价
- 把划线价当当前价
- Variant 不确定时猜价格
- 官网打不开时猜价格

## Issue body 格式

```json
{
  "targets": [
    {
      "region": "US",
      "product": "P2S",
      "variant": "P2S Combo",
      "url": "https://us.store.bambulab.com/products/p2s"
    }
  ]
}
```

字段：
- `region`: US / EU / UK / AU / CA
- `product`: 页面产品/产品系列名称
- `variant`: 有多个配置时填写界面准确名称；没有则留空
- `url`: 只放用户要求核验的官方链接

## 状态

- `VERIFIED`: 可以使用价格
- `ACCESS_FAILED`: 官网访问失败，不报价格
- `UNVERIFIED`: 页面有价格，但无法证明属于目标 Variant，不报价格
- `PRODUCT_MISMATCH`: 产品不匹配，不报价格
- `REDIRECTED_OTHER_PRODUCT`: 跳到其他产品，不报价格

## 证据

每次运行保留 30 天 Artifact：
- `reports/result.json`
- `reports/result.md`
- `reports/screenshots/*.png`
- `reports_console.txt`
