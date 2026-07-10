import app


def test_import_uploader_key_changes_after_success_report():
    state = {}

    assert app._get_import_uploader_key(state) == "import_wizard_files_0"

    app._store_import_result_and_reset_uploader(
        [{"状态": "成功", "文件名": "ok.xlsx"}],
        success_count=1,
        fail_count=0,
        state=state,
    )

    assert app._get_import_uploader_key(state) == "import_wizard_files_1"
    assert state["import_last_report"]["success_count"] == 1
    assert state["import_last_report"]["fail_count"] == 0
    assert state["import_last_report"]["rows"][0]["文件名"] == "ok.xlsx"


def test_import_uploader_key_changes_after_failure_report():
    state = {"import_uploader_token": 4}

    app._store_import_result_and_reset_uploader(
        [{"状态": "失败", "文件名": "bad.xlsx", "说明": "校验失败"}],
        success_count=0,
        fail_count=1,
        state=state,
    )

    assert app._get_import_uploader_key(state) == "import_wizard_files_5"
    assert state["import_last_report"]["fail_count"] == 1
    assert state["import_last_report"]["rows"][0]["说明"] == "校验失败"
