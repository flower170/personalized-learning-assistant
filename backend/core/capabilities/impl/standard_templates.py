"""
标准路径模板 + 统一资源推荐 —— 用户提供的成熟路径作为「路径规划标准」，对所有科目生效。

两部分能力：
1. 内置标准模板（数据分析 90 天精细化学习计划表、统计学 60 天学习路径…）：
   当 subject/topic 命中模板关键词时，WebPathPlanAgent 直接按模板结构生成
   stages + nodes，秒出结果（不依赖 LLM），保证输出稳定、与用户给出的标准一致。
   新增科目模板：照 DATA_ANALYSIS_TEMPLATE 结构追加 dict 并加入 STANDARD_TEMPLATES 即可。
2. attach_stage_resources(draft, subject)：对**任何科目**的草案统一挂阶段配套资源：
   - 视频 → B站按播放量最高的真实视频（点击直达，失败兜底官方搜索页）
   - 练习 → 编程类阶段（SQL/Python/Java…）推荐牛客网官方搜索链接
   数据分析模板自带的配套资源（数据集/环境等）保留，视频类条目替换为 top 播放真实视频。

模板设计：
- 一个模板 = { path_name, overall_goal, total_days_default, total_days_fast,
  stages: [{ title, description, expected_outcome, focus_points, days,
             resources: [{platform,title,url}], nodes: [{title,desc,days}] }] }
- 节点 days 为模板原始天数；build_standard_plan 按 daily_hours 缩放
  （<4h → total_days_default 90 天；>=4h → total_days_fast 60 天），
  保证 stages/nodes 天数之和 === 总周期，split_daily_tasks 不会截断。
- 模板可扩展：后续科目（如 Java 后端、前端）照这个结构追加即可。
"""
from __future__ import annotations

import asyncio
from urllib.parse import quote

DATA_ANALYSIS_TEMPLATE = {
    "match_keywords": ["数据分析", "数据运营", "数据分析师", "数据科学", "data analysis", "data analyst"],
    "path_name": "数据分析 90 天精细化学习路径（零基础｜求职导向）",
    "overall_goal": "简历拥有实战项目，能够投递数据分析师、数据运营岗位；能独立完成数据清洗、指标计算、SQL 取数、Python 分析与可视化，并产出业务分析报告",
    "market_demand": "数据分析/数据运营岗位：SQL 取数与业务查询是硬性要求，Python 数据处理与可视化是核心加分项，Power BI 看板与实战项目是面试重点",
    "total_days_default": 90,   # 每日 2~3 小时
    "total_days_fast": 60,      # 每日 4 小时以上可压缩到 60 天
    "stages": [
        {
            "title": "Excel 数据分析",
            "description": "熟练清洗数据、计算指标、制作报表",
            "expected_outcome": "拿到一份杂乱表格，可以独立完成清洗 + 多维度汇总报表",
            "focus_points": [
                "单元格操作：合并、边框、数据验证、条件格式",
                "基础函数：SUM/AVERAGE/IF/COUNTIF/SUMIF",
                "引用与名称管理：相对引用/绝对引用/混合引用",
                "查找函数：VLOOKUP/XLOOKUP、INDEX+MATCH",
                "条件统计：SUMIFS/COUNTIFS/AVERAGEIFS",
                "数据透视表：分组、筛选、值字段、计算字段、切片器",
                "图表制作：柱状/折线/饼图/组合图、图表美化",
                "动态图表与迷你图",
                "Power Query：去重、填充缺失值、拆分文本、逆透视",
                "数据清洗流程：格式统一、异常值处理、规范化",
            ],
            "days": 20,
            "resources": [
                {"platform": "数据集", "title": "Kaggle 公开电商销售数据集", "url": "https://www.kaggle.com/search?q=ecommerce+sales"},
                {"platform": "数据集", "title": "阿里云公开样本数据", "url": "https://tianchi.aliyun.com/dataset"},
                {"platform": "练习平台", "title": "Excel 自学网", "url": "http://www.excelhome.net/"},
            ],
            "nodes": [
                {"title": "Excel 基础：单元格操作、数据录入、基础函数（SUM、AVERAGE、IF）",
                 "desc": "自制销售表，完成基础营收统计", "days": 4},
                {"title": "核心查找函数：VLOOKUP/XLOOKUP、INDEX+MATCH、SUMIF/SUMIFS、COUNTIFS",
                 "desc": "多维度统计客户订单、按条件汇总销售额", "days": 5},
                {"title": "数据透视表：分组、筛选、值字段设置、计算字段",
                 "desc": "使用电商订单数据，统计月度、品类销量", "days": 5},
                {"title": "图表制作：折线、柱状、漏斗、组合图，图表美化",
                 "desc": "根据透视表结果绘制趋势分析图表", "days": 3},
                {"title": "Power Query、数据清洗：去重、填充缺失值、拆分文本",
                 "desc": "杂乱原始日志数据清洗，标准化格式", "days": 3},
            ],
        },
        {
            "title": "SQL 数据库",
            "description": "重中之重：熟练掌握 SQL 查询，能独立完成业务取数（第 21~45 天，25 天）",
            "expected_outcome": "熟悉完整 SQL 查询链路：单表→多表→窗口函数→业务场景，能独立完成日常取数与业务分析",
            "focus_points": [
                "基础语法：SELECT/WHERE/ORDER BY/LIMIT/DISTINCT",
                "聚合函数：SUM/COUNT/AVG/MAX/MIN",
                "分组查询：GROUP BY、HAVING 过滤",
                "多表连接：INNER JOIN / LEFT JOIN / RIGHT JOIN / FULL JOIN",
                "CASE WHEN 条件表达式",
                "子查询与派生表",
                "CTE 公共表表达式",
                "窗口函数：ROW_NUMBER/RANK/DENSE_RANK/LAG/LEAD",
                "日期与字符串函数",
                "业务 SQL：留存计算、连续签到、转化漏斗、TopN 取数",
            ],
            "days": 25,
            "resources": [
                {"platform": "练习网站", "title": "牛客网 SQL 题库", "url": "https://www.nowcoder.com/ta/sql"},
                {"platform": "练习网站", "title": "SQLZoo", "url": "https://sqlzoo.net/"},
                {"platform": "练习网站", "title": "LeetCode 数据库专区", "url": "https://leetcode.cn/problemset/database/"},
                {"platform": "本地环境", "title": "MySQL 8.0 安装包", "url": "https://dev.mysql.com/downloads/installer/"},
                {"platform": "数据集", "title": "经典 employees 样本库", "url": "https://github.com/datacharmer/test_db"},
            ],
            "nodes": [
                {"title": "SQL 基础：SELECT、WHERE、ORDER BY、LIMIT、DISTINCT、聚合函数 SUM/COUNT",
                 "desc": "单表查询，筛选用户、订单数据", "days": 6},
                {"title": "多表关联：INNER JOIN、LEFT JOIN、RIGHT JOIN；CASE WHEN、GROUP BY",
                 "desc": "用户表 + 订单表联查，统计每个用户消费总额", "days": 7},
                {"title": "进阶核心：子查询、CTE 临时表、窗口函数 ROW_NUMBER、RANK、DENSE_RANK",
                 "desc": "找出每个品类销量 TOP3 商品、用户首次下单标记", "days": 7},
                {"title": "综合刷题、常见业务 SQL 场景：留存计算、连续签到、转化漏斗",
                 "desc": "完成 20 道业务类 SQL 真题", "days": 5},
            ],
        },
        {
            "title": "Python 数据分析基础",
            "description": "Python 语法 + Numpy + Pandas，能自己处理真实数据（第 46~65 天，20 天）",
            "expected_outcome": "能用 Python + Pandas 独立完成数据的读取、清洗、分组聚合与透视分析",
            "focus_points": [
                "基础语法：变量、数据类型、运算符",
                "流程控制：if/for/while",
                "数据结构：列表/字典/元组/集合",
                "函数定义与模块导入",
                "文件读写：txt/csv 读取与写入",
                "NumPy：数组创建、切片、索引、向量化运算",
                "NumPy：缺失值处理、随机数生成",
                "Pandas：Series/DataFrame 创建与文件读取",
                "Pandas：筛选、去重、缺失值填充、类型转换",
                "Pandas：concat/merge 合并、groupby 分组聚合、透视表",
                "时间序列处理与日期索引",
            ],
            "days": 20,
            "resources": [
                {"platform": "运行环境", "title": "Anaconda（自带 Jupyter Notebook）", "url": "https://www.anaconda.com/download"},
                {"platform": "学习资料", "title": "《利用 Python 进行数据分析》官方仓库", "url": "https://github.com/wesm/pydata-book"},
                {"platform": "数据集", "title": "Kaggle 公开数据集", "url": "https://www.kaggle.com/datasets"},
            ],
            "nodes": [
                {"title": "Python 基础：变量、循环、判断、列表、字典、函数、文件读写",
                 "desc": "txt/csv 文件读取处理", "days": 6},
                {"title": "Numpy：数组创建、切片、数值运算、缺失值处理",
                 "desc": "批量数值计算", "days": 6},
                {"title": "Pandas 核心：Series、DataFrame，筛选、去重、缺失值填充、合并表",
                 "desc": "使用 Pandas 复现 Excel 透视表功能", "days": 5},
                {"title": "Pandas 进阶：分组聚合、透视表、时间处理",
                 "desc": "按日期统计用户流量、订单指标", "days": 3},
            ],
        },
        {
            "title": "统计学 + 数据可视化",
            "description": "统计基础 + Python 可视化 + BI 看板，学会用数据讲结论（第 66~78 天，13 天）",
            "expected_outcome": "能计算关键统计指标、用 Matplotlib/Seaborn 绘图，并用 Power BI 搭建交互式看板",
            "focus_points": [
                "描述统计：均值/中位数/四分位数/方差/标准差",
                "相关性分析：皮尔逊/斯皮尔曼相关系数",
                "概率基础：随机变量、期望、方差",
                "常见分布：正态分布/二项分布/泊松分布",
                "假设检验：t 检验/卡方检验、p 值、两类错误",
                "A/B 测试原理与样本量估计",
                "Matplotlib：基础绘图、子图、样式设置",
                "Seaborn：分布图/热力图/关系图",
                "图表配色与解读规范",
                "Power BI：导入数据、建模、度量值、交互式看板",
            ],
            "days": 13,
            "resources": [
                {"platform": "学习资料", "title": "《深入浅出统计学》（拒绝复杂公式）", "url": "https://book.douban.com/subject/10445952/"},
                {"platform": "可视化参考", "title": "Tableau Public 优秀案例", "url": "https://public.tableau.com/"},
            ],
            "nodes": [
                {"title": "描述统计、均值/中位数/四分位数、方差、相关性；概率基础；假设检验、A/B 测试原理",
                 "desc": "计算用户消费分布，分析指标相关性", "days": 6},
                {"title": "Python 可视化：Matplotlib、Seaborn 基础绘图",
                 "desc": "绘制分布图、趋势图、对比柱状图", "days": 4},
                {"title": "BI 工具（Power BI 优先）：导入数据、建模、度量值、交互式看板制作",
                 "desc": "搭建简易销售数据看板", "days": 3},
            ],
        },
        {
            "title": "业务分析思维 + 实战项目",
            "description": "简历核心：不要只跑代码，重点：提出问题→清洗数据→分析→得出结论→撰写分析报告（第 79~90 天，12 天）",
            "expected_outcome": "产出两份完整项目文档（代码 + 分析报告 + 可视化图表），简历可直接投递",
            "focus_points": [
                "业务分析思维：问题定义→指标选取→假设→验证",
                "转化漏斗分析与流失环节定位",
                "RFM 用户分层与运营策略",
                "复购率/留存率分析",
                "数据清洗与特征工程（针对项目数据）",
                "对比分析与归因分析",
                "分析报告结构：结论先行、图表辅助、建议落地",
                "业务建议的表达与可执行性",
                "面试项目讲解与话术准备",
            ],
            "days": 12,
            "resources": [
                {"platform": "数据集", "title": "Kaggle E-commerce Dataset", "url": "https://www.kaggle.com/search?q=ecommerce"},
                {"platform": "数据集", "title": "阿里天池公开数据集", "url": "https://tianchi.aliyun.com/dataset"},
                {"platform": "数据集", "title": "国家统计局公开数据（宏观分析）", "url": "https://data.stats.gov.cn/"},
                {"platform": "报告模板", "title": "标准数据分析报告结构参考", "url": "https://search.bilibili.com/all?keyword=数据分析报告模板"},
            ],
            "nodes": [
                {"title": "项目一：电商用户行为数据分析（Python+Pandas+可视化）——转化漏斗、RFM 用户分层、复购分析",
                 "desc": "产出完整分析报告 + 业务建议", "days": 5},
                {"title": "项目二：物流理赔风险数据分析（可选，差异化简历项目）——理赔特征、风险因素识别",
                 "desc": "产出分析报告 + 业务建议", "days": 4},
                {"title": "整理两份项目完整文档：代码 + 分析报告 + 可视化图表；梳理面试话术",
                 "desc": "简历项目 + 面试准备", "days": 3},
            ],
        },
    ],
}

# 标准模板注册表：subject/topic 命中的模板（按顺序匹配）
STANDARD_TEMPLATES = [DATA_ANALYSIS_TEMPLATE]


def match_template(subject: str = "", topic: str = "") -> dict | None:
    """匹配标准模板：subject 或 topic 含模板关键词即命中，返回模板 dict。"""
    haystack = f"{subject or ''} {topic or ''}".lower()
    for tmpl in STANDARD_TEMPLATES:
        for kw in tmpl.get("match_keywords", []):
            if kw.lower() in haystack:
                return tmpl
    return None


def _round_days(raw: int, factor: float) -> int:
    return max(1, round(raw * factor))


def build_standard_plan(subject: str, topic: str, daily_minutes: int) -> tuple[dict | None, int | None]:
    """按标准模板生成路径 plan（stages + nodes，均带天数/资源）。

    返回 (plan, total_days)；未命中模板返回 (None, None)。
    - daily_minutes >= 240（4 小时）→ 压缩到 total_days_fast（60 天）
    - 否则 → total_days_default（90 天）
    """
    tmpl = match_template(subject, topic)
    if not tmpl:
        return None, None

    daily_hours = (daily_minutes or 90) / 60.0
    if daily_hours >= 4:
        factor = tmpl["total_days_fast"] / tmpl["total_days_default"]
    else:
        factor = 1.0

    stages, nodes = [], []
    for si, st in enumerate(tmpl["stages"], 1):
        raw_nodes = st.get("nodes", [])
        scaled_days = [_round_days(n.get("days", 1), factor) for n in raw_nodes]
        stage_days = sum(scaled_days)

        stages.append({
            "stage": si,
            "title": st.get("title", f"阶段{si}"),
            "description": st.get("description", ""),
            "estimated_days": stage_days,
            "focus_points": st.get("focus_points", []) or [],
            "expected_outcome": st.get("expected_outcome", ""),
            # 配套资源（视频/练习网站/数据集）带可点击 URL，前端按链接渲染
            "resources": [dict(r) for r in (st.get("resources") or [])],
        })
        for ni, n in enumerate(raw_nodes):
            nodes.append({
                "node_id": f"step_{si:02d}_{ni + 1:02d}",
                "title": n.get("title", ""),
                "description": n.get("desc", ""),
                "estimated_days": scaled_days[ni],
                "resource_types": ["lecture", "exercise", "oj"],
                "reason": n.get("desc", ""),
                "resources": [],   # 配套资源挂在阶段级，节点不重复
            })

    plan = {
        "path_name": tmpl.get("path_name", f"{subject}学习路径"),
        "overall_goal": tmpl.get("overall_goal", f"系统掌握{subject}"),
        "market_demand": tmpl.get("market_demand", ""),
        "stages": stages,
        "nodes": nodes,
    }
    total_days = sum(st.get("estimated_days", 0) for st in stages)
    return plan, total_days


STATISTICS_TEMPLATE = {
    "match_keywords": ["统计学", "数理统计", "统计推断", "应用统计", "statistics"],
    "path_name": "统计学 60 天学习路径（零基础｜应用导向）",
    "overall_goal": "系统掌握描述统计、概率论、推断统计与回归分析，能独立完成一份数据调研/统计分析报告并给出结论",
    "market_demand": "统计学/数据分析岗位：假设检验、A/B 实验、回归建模是高频考察点；SPSS/Python 统计分析能力与报告是简历加分项",
    "total_days_default": 60,
    "total_days_fast": 45,
    "stages": [
        {
            "title": "描述性统计与数据可视化",
            "description": "把杂乱数据整理成图和表，用统计量概括数据特征",
            "expected_outcome": "拿到一份原始数据，能独立完成清洗、分组汇总、图表与描述统计量输出",
            "focus_points": [
                "数据类型与测量尺度（定类/定序/定距/定比）",
                "频数分布表与统计图表（直方图/箱线图/柱状图）",
                "集中趋势：均值/中位数/众数及其适用场景",
                "离散程度：极差/方差/标准差/四分位距",
                "分布形态：偏度与峰度",
                "相关系数与散点图",
                "Excel/SPSS 描述统计输出实操",
            ],
            "days": 12,
            "resources": [
                {"platform": "数据集", "title": "国家统计局公开数据", "url": "https://data.stats.gov.cn/"},
                {"platform": "数据集", "title": "Kaggle 统计练习数据集", "url": "https://www.kaggle.com/datasets"},
                {"platform": "工具", "title": "SPSS Statistics 官方", "url": "https://www.ibm.com/products/spss-statistics"},
                {"platform": "工具", "title": "Anaconda（Jupyter + Python 统计库）", "url": "https://www.anaconda.com/download"},
                {"platform": "学习资料", "title": "《深入浅出统计学》", "url": "https://book.douban.com/subject/10445952/"},
            ],
            "nodes": [
                {"title": "统计基础：数据类型、总体/样本、统计图表（柱状/箱线/直方图）",
                 "desc": "对一份销售数据画图并描述特征", "days": 4},
                {"title": "集中趋势：均值、中位数、众数及其适用场景",
                 "desc": "计算多组数据的均值/中位数并比较", "days": 4},
                {"title": "离散程度：方差、标准差、极差、四分位距；描述统计软件实操",
                 "desc": "用 SPSS/Python 输出完整描述统计表", "days": 4},
            ],
        },
        {
            "title": "概率论基础",
            "description": "概率、随机变量、常见分布，为推断统计打地基",
            "expected_outcome": "能识别随机变量分布、会算常见概率，理解大数定律与中心极限定理",
            "focus_points": [
                "随机事件与概率定义",
                "条件概率与事件独立性",
                "全概率公式与贝叶斯公式",
                "离散型随机变量与分布律",
                "连续型随机变量与概率密度函数",
                "期望与方差的定义与计算",
                "正态分布、二项分布、泊松分布",
                "大数定律与中心极限定理",
            ],
            "days": 12,
            "resources": [
                {"platform": "学习资料", "title": "《概率论与数理统计》（浙大版）", "url": "https://book.douban.com/subject/24719073/"},
                {"platform": "练习平台", "title": "LeetCode 概率/统计题（可选）", "url": "https://leetcode.cn/problemset/"},
                {"platform": "工具", "title": "GeoGebra 概率分布模拟", "url": "https://www.geogebra.org/"},
            ],
            "nodes": [
                {"title": "概率基础：随机事件、条件概率、全概率公式",
                 "desc": "完成 10 道经典概率计算题", "days": 4},
                {"title": "随机变量与分布：离散型/连续型、期望与方差",
                 "desc": "计算常见分布的期望方差", "days": 4},
                {"title": "常见分布与极限定理：正态/二项/泊松、大数定律、中心极限定理",
                 "desc": "用模拟验证中心极限定理", "days": 4},
            ],
        },
        {
            "title": "推断统计",
            "description": "从样本推断总体：参数估计 + 假设检验，核心是检验思路",
            "expected_outcome": "能独立完成一次假设检验并正确解读 p 值，理解两类错误与 A/B 实验",
            "focus_points": [
                "抽样分布与标准误",
                "点估计与估计量的性质",
                "区间估计与置信区间",
                "假设检验的基本思想与步骤",
                "t 检验：单样本/独立样本/配对样本",
                "卡方检验",
                "p 值与两类错误（α/β）",
                "检验功效与样本量估计",
                "A/B 测试设计与结果解读",
            ],
            "days": 16,
            "resources": [
                {"platform": "练习平台", "title": "A/B 测试样本量计算器", "url": "https://www.evanmiller.org/ab-testing/sample-size.html"},
                {"platform": "数据集", "title": "Kaggle A/B 测试数据集", "url": "https://www.kaggle.com/datasets"},
                {"platform": "工具", "title": "SciPy 统计检验文档", "url": "https://docs.scipy.org/doc/scipy/reference/stats.html"},
            ],
            "nodes": [
                {"title": "抽样分布与标准误",
                 "desc": "抽样分布模拟练习", "days": 4},
                {"title": "参数估计：点估计与置信区间",
                 "desc": "计算样本均值的置信区间", "days": 4},
                {"title": "假设检验：t 检验、卡方检验、p 值与两类错误",
                 "desc": "完成 3 组真实数据检验", "days": 5},
                {"title": "A/B 测试设计与显著性解读",
                 "desc": "设计一次电商 A/B 实验并解读结果", "days": 3},
            ],
        },
        {
            "title": "相关与回归分析",
            "description": "量化变量间关系，用回归做预测与归因",
            "expected_outcome": "能做相关分析、建立一元/多元线性回归并解读系数与显著性",
            "focus_points": [
                "相关系数计算与显著性检验",
                "散点图与变量关系可视化",
                "一元线性回归与最小二乘估计",
                "R² 与拟合优度",
                "回归系数检验与置信区间",
                "多元线性回归",
                "多重共线性与变量选择",
                "残差诊断与模型假设检验",
                "分类变量处理（虚拟变量）",
            ],
            "days": 12,
            "resources": [
                {"platform": "数据集", "title": "Kaggle 回归练习数据集", "url": "https://www.kaggle.com/datasets"},
                {"platform": "学习资料", "title": "《回归分析》（经典教材）", "url": "https://book.douban.com/subject/1440637/"},
            ],
            "nodes": [
                {"title": "相关分析：相关系数、散点图、显著性检验",
                 "desc": "分析两个变量的相关强度", "days": 4},
                {"title": "一元线性回归：最小二乘、R²、显著性",
                 "desc": "建立一元回归并解读", "days": 4},
                {"title": "多元回归与模型诊断：多重共线性、残差分析",
                 "desc": "完成一次多元回归分析报告", "days": 4},
            ],
        },
        {
            "title": "统计学综合实战",
            "description": "全流程串起来：问题→数据→分析→结论→报告（简历项目）",
            "expected_outcome": "能独立完成一份带统计结论的业务分析报告（简历项目）",
            "focus_points": [
                "统计建模完整流程：问题→数据→分析→结论",
                "数据清洗与预处理",
                "描述统计与推断统计的综合运用",
                "回归模型构建与结果解读",
                "结果解读与业务结论落地",
                "可视化报告撰写",
                "面试项目讲解与话术准备",
            ],
            "days": 8,
            "resources": [
                {"platform": "数据集", "title": "阿里天池公开数据集", "url": "https://tianchi.aliyun.com/dataset"},
                {"platform": "数据集", "title": "Kaggle 综合数据集", "url": "https://www.kaggle.com/datasets"},
                {"platform": "报告模板", "title": "统计分析报告结构参考", "url": "https://search.bilibili.com/all?keyword=数据分析报告模板"},
            ],
            "nodes": [
                {"title": "项目一：描述统计 + 推断统计完成一份真实数据调研（如用户消费行为）",
                 "desc": "输出假设检验结论", "days": 3},
                {"title": "项目二：回归建模预测（如房价/销量）并做模型诊断",
                 "desc": "输出回归模型报告", "days": 3},
                {"title": "整理完整报告：代码 + 图表 + 统计结论 + 业务建议，梳理面试话术",
                 "desc": "简历项目 + 面试准备", "days": 2},
            ],
        },
    ],
}

# 标准模板注册表：subject/topic 命中的模板（按顺序匹配）
STANDARD_TEMPLATES = [DATA_ANALYSIS_TEMPLATE, STATISTICS_TEMPLATE]


# ==================== 统一资源推荐（所有科目生效） ====================

# 阶段标题命中这些词 → 视为编程/技术类学习，推荐牛客网练习链接
_STAGE_CODING_HINTS = (
    "sql", "数据库", "mysql", "postgresql", "python", "pandas", "numpy", "java", "c++",
    "c语言", "javascript", "typescript", "前端", "后端", "全栈", "编程", "代码", "算法",
    "数据结构", "爬虫", "数据清洗", "窗口函数", "分组聚合", "数据查询", "bi",
)


def _fmt_play(play) -> str:
    """播放量格式化：123456 → 12.3万"""
    try:
        p = int(play or 0)
        if p >= 100000000:
            return f"{p / 100000000:.1f}亿"
        if p >= 10000:
            return f"{p / 10000:.1f}万"
        return str(p)
    except Exception:
        return str(play or 0)


async def _recommend_bilibili_top(keyword: str) -> dict | None:
    """B站按播放量最高的真实视频；失败兜底官方搜索页（链接永远可点）。"""
    kw = (keyword or "").strip()
    if not kw:
        return None
    try:
        from core.utils.video_cover import search_bilibili_videos
        videos = await search_bilibili_videos(kw, page=1, max_results=3)
    except Exception:
        videos = []
    if videos:
        v = videos[0]
        title = (v.get("title") or "").strip()
        if len(title) > 28:
            title = title[:27] + "…"
        return {
            "platform": "视频",
            "title": f"{title}（{_fmt_play(v.get('play'))}播放·{v.get('author', '')}）",
            "url": v.get("url") or f"https://search.bilibili.com/all?keyword={quote(kw)}",
        }
    return {
        "platform": "视频",
        "title": f"B站搜索：{kw}（按播放量最高）",
        "url": f"https://search.bilibili.com/all?keyword={quote(kw)}",
    }


async def attach_stage_resources(draft: dict, subject: str = "") -> dict:
    """给草案统一挂配套资源（点击直达）。

    规则：
    - 视频：整个路径只推荐一个 → 按科目搜 B站取播放量最高的真实视频，挂到 draft['recommended_video']
    - 练习：阶段标题含编程/技术关键词 → 加牛客网官方搜索链接（已有牛客链接则跳过）
    - 其他配套（数据集/环境/学习资料）原样保留，不再每阶段挂视频
    视频搜索失败自动兜底，不影响草案生成。
    """
    stages = draft.get("stages", [])

    # 1) 路径级推荐视频（只一个，按科目搜 B站播放量最高）
    kw = (subject or draft.get("topic") or "").strip()
    draft["recommended_video"] = await _recommend_bilibili_top(kw) if kw else None

    # 2) 阶段配套：清掉历史残留的视频条目；编程/技术类阶段补牛客练习链接
    for s in stages:
        kept = [r for r in (s.get("resources") or [])
                if str(r.get("platform", "")).strip() != "视频"]
        kw2 = s.get("title", "")
        if kw2 and any(h in str(kw2).lower() for h in _STAGE_CODING_HINTS):
            if not any("nowcoder" in str(r.get("url", "")) for r in kept):
                try:
                    from core.capabilities.impl.practice_search import PLATFORM_CONFIG
                    nk_url = PLATFORM_CONFIG["牛客"]["search_url"](kw2)
                except Exception:
                    nk_url = f"https://www.nowcoder.com/search?query={quote(kw2)}"
                kept.append({"platform": "练习网站", "title": f"牛客网刷题：{kw2}", "url": nk_url})
        s["resources"] = kept
    return draft


__all__ = [
    "match_template", "build_standard_plan", "attach_stage_resources",
    "DATA_ANALYSIS_TEMPLATE", "STATISTICS_TEMPLATE", "STANDARD_TEMPLATES",
]
