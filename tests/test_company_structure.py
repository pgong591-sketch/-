from sqlalchemy import text

from src.company_structure import EXTERNAL_CATEGORY, MANAGED_CATEGORY, get_company_structure_view
from src.db_connection import get_session, init_database


def test_company_structure_view_splits_managed_and_external():
    init_database()
    session = get_session()
    try:
        session.execute(text("""
            INSERT OR REPLACE INTO companies
                (code, name, short_name, parent_code, level, tree_path, status, is_consolidated)
            VALUES
                ('ROOT', '多维教育集团', '集团', NULL, 0, '/ROOT', 1, 1),
                ('101', '广东多维教育科技集团有限公司', '集团公司', 'ROOT', 1, '/ROOT/101', 1, 1),
                ('1010101', '东莞非学科管理中心', '非学科管理中心', '101', 2, '/ROOT/101/1010101', 1, 1),
                ('1020401', '莞城鸿福尔遇书馆', '莞城鸿福尔遇书馆', '101', 2, '/ROOT/101/1020401', 1, 1),
                ('1010801', '东莞市望牛墩多维学校', '多维学校', '101', 2, '/ROOT/101/1010801', 1, 1),
                ('101010120', '莞城小学部', '莞城小学部', '101', 2, '/ROOT/101/101010120', 1, 1),
                ('101010102', '华凯校区', '华凯校区', '101', 2, '/ROOT/101/101010102', 1, 1),
                ('1010201', '深圳国际教育', '深圳国际教育', '101', 2, '/ROOT/101/1010201', 1, 1),
                ('1010502', '东莞加佳物业管理有限公司', '东莞加佳物业', '101', 2, '/ROOT/101/1010502', 1, 1),
                ('10112', '东莞赫布科技有限公司', '赫布科技', '101', 2, '/ROOT/101/10112', 1, 1),
                ('201', '外部合作项目A', '外部项目A', '101', 2, '/ROOT/101/201', 1, 0)
        """))
        session.execute(text("""
            INSERT OR REPLACE INTO dim_company
                (company_id, company_name, business_group, business_type, region, is_operational)
            VALUES
                ('1010101', '东莞非学科管理中心', '非学科素质中心模块', '管理中心', '东莞', 1),
                ('1020401', '莞城鸿福尔遇书馆', '尔遇书馆模块', '书馆', '莞城', 1),
                ('1010801', '东莞市望牛墩多维学校', '', '学校', '望牛墩', 1),
                ('101010120', '莞城小学部', '', '小学', '莞城', 1),
                ('101010102', '华凯校区', '', '校区', '', 1),
                ('1010201', '深圳国际教育', '', '其他', '深圳', 1),
                ('1010502', '东莞加佳物业管理有限公司', '', '物业', '东莞', 1),
                ('10112', '东莞赫布科技有限公司', '', '科技公司', '东莞', 1),
                ('201', '外部合作项目A', '外部投资模块', '其他', '', 0)
        """))
        session.execute(text("""
            INSERT INTO ownership
                (parent_code, sub_code, ownership_pct, effective_date, is_control)
            VALUES
                ('101', '201', 30, '20260101', 0)
        """))
        session.commit()
    finally:
        session.close()

    df = get_company_structure_view()
    managed = df[df["management_category"] == MANAGED_CATEGORY]
    external = df[df["management_category"] == EXTERNAL_CATEGORY]

    assert "1010101" in managed["company_code"].tolist()
    assert "1020401" in managed["company_code"].tolist()
    assert managed[managed["company_code"] == "1010101"].iloc[0]["display_module"] == "非学科素质中心模块"
    assert managed[managed["company_code"] == "1020401"].iloc[0]["display_module"] == "尔遇书馆模块"
    assert managed[managed["company_code"] == "1010801"].iloc[0]["display_module"] == "学校模块"
    assert managed[managed["company_code"] == "101010120"].iloc[0]["display_module"] == "未分配模块"
    assert managed[managed["company_code"] == "101010102"].iloc[0]["display_module"] == "非学科素质中心模块"
    assert managed[managed["company_code"] == "1010201"].iloc[0]["display_module"] == "国际教育模块"
    assert managed[managed["company_code"] == "1010502"].iloc[0]["display_module"] == "物业公司"
    assert managed[managed["company_code"] == "10112"].iloc[0]["display_module"] == "职能公司模块"
    assert external.iloc[0]["company_code"] == "201"
    assert external.iloc[0]["display_module"] == "单项目"
