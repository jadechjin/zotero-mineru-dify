# Config Schema Reference

Source: `services/config_schema.py`

## Categories

### zotero

| Key | Type | Default | Sensitive | Label |
|-----|------|---------|-----------|-------|
| mcp_url | str | `http://127.0.0.1:23120/mcp` | No | MCP 连接地址 |
| collection_keys | str | `""` | No | 分组 Key（逗号分隔） |
| collection_recursive | bool | `true` | No | 递归子分组 |
| collection_page_size | int [1-500] | `50` | No | 分页大小 |

### mineru

| Key | Type | Default | Sensitive | Label |
|-----|------|---------|-----------|-------|
| api_token | str | `""` | Yes | API Token |
| poll_timeout_s | int [60-86400] | `7200` | No | 轮询超时（秒） |

### dify

| Key | Type | Default | Sensitive | Label |
|-----|------|---------|-----------|-------|
| api_key | str | `""` | Yes | Dataset API Key |
| base_url | str | `https://api.dify.ai/v1` | No | Base URL |
| dataset_name | str | `Zotero Literature` | No | 知识库名称 |
| pipeline_file | str | `""` | No | Pipeline 文件路径 |
| process_mode | select [custom, automatic] | `custom` | No | 处理模式 |
| segment_separator | str | `\n\n` | No | 分段分隔符 |
| segment_max_tokens | int [100-10000] | `800` | No | 段最大 Token |
| chunk_overlap | int [0-1000] | `0` | No | 分段重叠 |
| parent_mode | str | `paragraph` | No | 父级模式 |
| subchunk_separator | str | `\n` | No | 子分段分隔符 |
| subchunk_max_tokens | int [50-5000] | `256` | No | 子段最大 Token |
| subchunk_overlap | int [0-500] | `0` | No | 子段重叠 |
| remove_extra_spaces | bool | `true` | No | 去除多余空格 |
| remove_urls_emails | bool | `false` | No | 去除 URL/邮箱 |
| index_max_wait_s | int [60-7200] | `1800` | No | 索引等待上限（秒） |
| doc_form | str | `""` | No | 文档形式 |
| doc_language | str | `""` | No | 文档语言 |
| upload_delay | int [0-30] | `1` | No | 上传间隔（秒） |

### md_clean

| Key | Type | Default | Sensitive | Label |
|-----|------|---------|-----------|-------|
| enabled | bool | `true` | No | 启用清洗 |
| collapse_blank_lines | bool | `true` | No | 压缩空行 |
| strip_html | bool | `true` | No | 移除 HTML |
| remove_control_chars | bool | `true` | No | 移除控制字符 |
| remove_image_placeholders | bool | `true` | No | 移除图片占位 |
| remove_page_numbers | bool | `false` | No | 移除页码 |
| remove_watermark | bool | `false` | No | 移除水印 |
| watermark_patterns | str | `""` | No | 水印正则（逗号分隔） |

### smart_split

| Key | Type | Default | Sensitive | Label |
|-----|------|---------|-----------|-------|
| enabled | bool | `true` | No | 启用智能分割 |
| split_marker | str | `<!--split-->` | No | 分割标记 |
| max_length | int [200-10000] | `1200` | No | 最大段落长度 |
| min_length | int [50-5000] | `300` | No | 最小段落长度 |
| min_split_score | float [0-50] | `7.0` | No | 最小分割得分 |
| heading_score_bonus | float [0-50] | `10.0` | No | 标题加分 |
| sentence_end_score_bonus | float [0-50] | `6.0` | No | 句尾加分 |
| sentence_integrity_weight | float [0-50] | `8.0` | No | 句子完整性权重 |
| length_score_factor | int [1-1000] | `100` | No | 长度评分因子 |
| search_window | int [1-20] | `5` | No | 搜索窗口 |
| heading_after_penalty | float [0-50] | `12.0` | No | 标题后惩罚 |
| force_split_before_heading | bool | `true` | No | 标题前强制分割 |
| heading_cooldown_elements | int [0-10] | `2` | No | 标题冷却元素数 |
| custom_heading_regex | str | `""` | No | 自定义标题正则（逗号分隔） |

## ENV_KEY_MAP

Maps 32 `.env` variable names to `(category, key)` tuples. Full list in `services/config_schema.py:70-103`.
