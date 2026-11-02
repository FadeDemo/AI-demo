# 检索基础交互实验

本项目配套 [RAG 检索基础](../../notes/rag/index.md)。直接打开 [index.html](index.html) 即可使用，不需要安装网页依赖或启动服务。页面没有外部字体、远程脚本和模型请求，也不读取本地资料或保存操作记录。

## 三个实验

| 入口                             | 操作                                     | 要观察的现象                                             |
| -------------------------------- | ---------------------------------------- | -------------------------------------------------------- |
| [向量](index.html#vectors)       | 调整文档向量的方向与长度，可选择先归一化 | 方向不变时余弦不变，点积会受长度影响；零向量的余弦无定义 |
| [排名与指标](index.html#metrics) | 上下移动文档、改变 K、切换资料无答案     | 第一篇相关文档的位置与找回的相关文档数量各影响什么指标   |
| [排名融合](index.html#fusion)    | 改变 RRF 常数 c                          | 同一篇文档的两路贡献怎样相加，缺席一路时贡献为零         |

向量和排名由教学数据直接给定，页面没有执行真实 Embedding、关键词搜索或自动相关性判断。真实检索实验按课程要求在实践项目中完成。

## 计算约定

- 向量实验的问题为 `[1, 0]`，文档向量由角度和长度生成。勾选归一化后，非零文档向量先缩放为单位长度，图与指标使用同一条处理后的向量。
- Precision@K 固定除以 K，返回不足 K 篇时不改变分母。Recall 与 RR 在相关集合为空时显示不适用；Precision 可计算为 0。无答案问题的三项数值都不混入有答案问题的均值。
- 排名实验展示单个问题的 RR@K。多题平均后才称为 MRR@K。
- RRF 的位置从 1 开始，两路等权，常数 c 为正。分数并列时按文档编号升序排列，显示小数的舍入不影响排序。

## 文件与检查

`index.html` 保存页面结构与样式，`lab.js` 负责计算和交互。`lab.test.cjs` 用 Node.js 自带的测试工具核对手算值、缺席排名、指标分母和边界情况，不访问浏览器或网络。

在本目录运行计算测试。

```shell
node --test lab.test.cjs
```

在仓库根目录使用已有质量工具检查页面和文档。

```shell
node_modules/.bin/prettier --check projects/retrieval-usage-lab/README.md projects/retrieval-usage-lab/index.html projects/retrieval-usage-lab/lab.js projects/retrieval-usage-lab/lab.test.cjs
node_modules/.bin/html-validate projects/retrieval-usage-lab/index.html
node_modules/.bin/markdownlint-cli2 projects/retrieval-usage-lab/README.md
```

计算测试不能代替浏览器检查。页面还应在桌面与窄屏宽度检查滑块、键盘操作、排序按钮、表格和向量箭头。所有图形按实际容器宽度绘制，数值变化以页面当前输入为准。
