import pandas as pd
from sqlalchemy import text

from src.company_dimension import (
    BUSINESS_GROUP_OPTIONS,
    get_company_dimensions,
    prune_dim_company_orphans,
    save_company_dimensions,
    seed_dim_company_from_companies,
)
from src.db_connection import get_session, init_database


def test_seed_dim_company_from_companies():
    init_database()
    session = get_session()
    try:
        session.execute(text("""
            INSERT OR REPLACE INTO companies
                (code, name, short_name, parent_code, level, status)
            VALUES
                ('101', '广东多维教育科技集团有限公司', '集团', NULL, 1, 1),
                ('101010120', '莞城小学部', '莞城小学部', '101', 4, 1)
        """))
        session.commit()
    finally:
        session.close()

    inserted = seed_dim_company_from_companies()
    assert inserted == 2

    df = get_company_dimensions()
    row = df[df["company_id"] == "101010120"].iloc[0]
    assert row["business_group"] == ""
    assert row["business_type"] == "小学"
    assert row["region"] == "莞城"
    assert row["is_operational"] == "是"


def test_save_company_dimensions_replace():
    init_database()
    session = get_session()
    try:
        session.execute(text("""
            INSERT OR REPLACE INTO companies
                (code, name, short_name, parent_code, level, status)
            VALUES
                ('1020401', '莞城鸿福尔遇书馆', '莞城鸿福尔遇书馆', NULL, 4, 1)
        """))
        session.commit()
    finally:
        session.close()

    edited = pd.DataFrame([{
        "公司编码": "1020401",
        "公司名称": "莞城鸿福尔遇书馆",
        "所属板块": "尔遇书馆模块",
        "业态类型": "书馆",
        "所属区域": "莞城",
        "运营主体": "否",
    }])
    saved = save_company_dimensions(edited)
    assert saved == 1

    df = get_company_dimensions()
    row = df[df["company_id"] == "1020401"].iloc[0]
    assert row["business_group"] == "尔遇书馆模块"
    assert row["business_type"] == "书馆"
    assert row["is_operational"] == "否"


def test_business_group_options_only_include_formal_modules():
    assert BUSINESS_GROUP_OPTIONS == [
        "",
        "非学科素质中心模块",
        "尔遇书馆模块",
        "学校模块",
        "幼儿园模块",
        "托育模块",
        "文旅模块",
        "尔遇书城模块",
        "少年宫模块",
        "国际教育模块",
        "职能公司模块",
        "物业公司",
        "外部投资模块",
    ]


def test_infer_new_business_group_modules():
    init_database()
    session = get_session()
    try:
        session.execute(text("""
            INSERT OR REPLACE INTO companies
                (code, name, short_name, parent_code, level, status)
            VALUES
                ('1010201', '深圳国际教育', '深圳国际教育', NULL, 2, 1),
                ('1010502', '东莞加佳物业管理有限公司', '东莞加佳物业', NULL, 2, 1),
                ('10112', '东莞赫布科技有限公司', '赫布科技', NULL, 2, 1)
        """))
        session.commit()
    finally:
        session.close()

    seed_dim_company_from_companies()
    df = get_company_dimensions().set_index("company_id")
    assert df.loc["1010201", "business_group"] == "国际教育模块"
    assert df.loc["1010502", "business_group"] == "物业公司"
    assert df.loc["10112", "business_group"] == "职能公司模块"


def test_get_company_dimensions_prunes_deleted_company_rows():
    init_database()
    session = get_session()
    try:
        session.execute(text("""
            INSERT OR REPLACE INTO companies
                (code, name, short_name, parent_code, level, tree_path, status)
            VALUES
                ('101', '集团公司', '集团公司', NULL, 1, '/101', 1),
                ('102', '待删除公司', '待删除公司', '101', 2, '/101/102', 1)
        """))
        session.execute(text("""
            INSERT OR REPLACE INTO dim_company
                (company_id, company_name, business_group, business_type, region, is_operational)
            VALUES
                ('101', '集团公司', '', '集团', '', 0),
                ('102', '待删除公司', '', '其他', '', 1)
        """))
        session.execute(text("DELETE FROM companies WHERE code = '102'"))
        session.commit()
    finally:
        session.close()

    assert prune_dim_company_orphans() == 1
    df = get_company_dimensions()
    assert "102" not in df["company_id"].tolist()
    assert df["tree_path"].isna().sum() == 0
