# 包装说明版位的选择实验与共用模板

当前资料覆盖成对图稿选择和制版资源。记录均为合成数据，使用 UTF-8 编码及带列名的 CSV。

## 运行

使用 Python 3.11。分析依赖在 `requirements.txt` 中锁定，本地环境可运行 `python3 -m pip install -r requirements.txt` 安装。在项目根目录查看文件列和记录数，并核对交接格式。

```sh
python3 inspect_inputs.py data
python3 -m unittest discover -s tests -v
```

## 记录约定

choice 的值为每对里被选中的图稿号，none 是两份都不选，空值是未观察。meaning 的 1 代表能正确区分两种糖声明，confidence 为 1 至 4 的确信度。每位参与者可参加不同顺序的分块，分块中列出实际候选和出现概率。模板容量单位是版面格，一个模板的同一个版位可容纳完全相同的固定文字，文字不同则不能共用。

- `designs.csv` 图稿属性，保留各商品瓶型及文字共用限制。
- `blocks.csv` 每块的成对候选与分配概率。
- `trials.csv` 个人每轮实际显示、选择和两份图稿的理解票据。
- `templates.csv` 候选制版模板及允许商品，斜杠表示并列。
- `corrections.csv` 图稿属性更正。
- `policy.csv` 分商品误解上限和分读者组最低理解门槛，星号表示不分组。
