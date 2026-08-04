# 历史互动数据导入示例

本目录提供「活跃度分析 → 发布时间推荐」链路的导入示例，供本地联调和答辩演示使用。

## 文件说明

| 文件 | source_type | 说明 |
| --- | --- | --- |
| `demo-account-history-SIMULATED.csv` | `ACCOUNT_HISTORY` | **合成演示数据（SIMULATED）**，由 `generate_demo_history.py` 生成，仅用于验证导入、清洗与统计流程，**不是任何真实平台的数据**。 |

> 演示数据导入后，前端「发布时间」页与推荐结果都会显示样本来源与样本量；
> 请勿把这些数字当作真实运营结论。

## 使用真实公开数据集

系统的「公开数据基线」支持导入真实的公开研究数据集，请自行下载后按下表映射字段：

### YouTubeDurationData（sTechLab）

- 仓库：<https://github.com/sTechLab/YouTubeDurationData>
- 导入时 `source_type` 必须填 `YOUTUBE_PUBLIC_SAMPLE`。
- 系统会把该来源标注为「YouTube 公开样本（非国内平台数据）」，
  只用于冷启动的时段先验参考，**不会**展示为微博 / 小红书 / 微信公众号的真实数据。

推荐字段映射：

| 系统字段 | 数据集列 |
| --- | --- |
| `platform` | 固定填 `YOUTUBE`（或在导入表单里设置默认平台） |
| `account_id` | `channelId` |
| `content_type` | `categoryId` |
| `publish_time` | `publishedAt` |
| `views` | `viewCount` |
| `likes` | `likeCount` |
| `comments` | `commentCount` |
| `favorites` | `favoriteCount` |

### 其他公开互动数据集

任何包含「发布时间 + 浏览/曝光 + 点赞/评论/分享/收藏」的公开数据集都可以导入，
`source_type` 选择 `PUBLIC_BASELINE` 或 `RESEARCH_DATASET`。

## 导入方式

1. 打开「发布时间」页 → 「历史数据导入」。
2. 上传 CSV / XLSX，系统会自动猜测字段映射并给出预览、缺失值与重复行统计。
3. 确认映射后提交，导入结果会记录成批次，可随时回看或删除。

## 重新生成演示数据

```bat
cd sample-data\history
python generate_demo_history.py
```
