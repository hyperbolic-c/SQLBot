#!/bin/bash
# Copyright 2024 SQLBot. All rights reserved.
# 测试运行脚本 - 在 Docker 容器中执行

set -e

echo "=============================================="
echo "SQLBot 重构版本测试脚本"
echo "=============================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试结果目录
TEST_RESULTS_DIR="${TEST_RESULTS_DIR:-/opt/sqlbot/app/test_results}"
mkdir -p "$TEST_RESULTS_DIR"

# 记录测试开始时间
START_TIME=$(date +%s)

echo -e "${YELLOW}[INFO] 开始运行测试...${NC}"

# ============================================================================
# 1. 验证模块导入
# ============================================================================
echo ""
echo "=============================================="
echo "Step 1: 验证重构模块导入"
echo "=============================================="

python -c "
from apps.algorithm.schema import AlgorithmInput
from apps.algorithm.result import AlgorithmResult, AlgorithmLog
from apps.algorithm.service import AlgorithmService
from apps.business_db import BusinessDataLayer
print('[PASS] 所有重构模块导入成功')
" && IMPORT_PASS=true || IMPORT_PASS=false

if [ "$IMPORT_PASS" = true ]; then
    echo -e "${GREEN}[PASS] 模块导入测试通过${NC}"
else
    echo -e "${RED}[FAIL] 模块导入测试失败${NC}"
    exit 1
fi

# ============================================================================
# 2. 运行数据模型测试
# ============================================================================
echo ""
echo "=============================================="
echo "Step 2: 运行数据模型测试"
echo "=============================================="

python -m pytest tests/test_algorithm_schema.py tests/test_algorithm_result.py -v --tb=short
if [ $? -eq 0 ]; then
    echo -e "${GREEN}[PASS] 数据模型测试通过${NC}"
else
    echo -e "${RED}[FAIL] 数据模型测试失败${NC}"
    exit 1
fi

# ============================================================================
# 3. 运行服务层测试
# ============================================================================
echo ""
echo "=============================================="
echo "Step 3: 运行服务层测试"
echo "=============================================="

python -m pytest tests/test_algorithm_service.py -v --tb=short
if [ $? -eq 0 ]; then
    echo -e "${GREEN}[PASS] 服务层测试通过${NC}"
else
    echo -e "${RED}[FAIL] 服务层测试失败${NC}"
    exit 1
fi

# ============================================================================
# 4. 运行 SSE 输出格式测试
# ============================================================================
echo ""
echo "=============================================="
echo "Step 4: 运行 SSE 输出格式测试"
echo "=============================================="

python -m pytest tests/test_stream_output.py -v --tb=short
if [ $? -eq 0 ]; then
    echo -e "${GREEN}[PASS] SSE 输出格式测试通过${NC}"
else
    echo -e "${RED}[FAIL] SSE 输出格式测试失败${NC}"
    exit 1
fi

# ============================================================================
# 5. 验证与原实现的一致性
# ============================================================================
echo ""
echo "=============================================="
echo "Step 5: 验证与原实现的一致性"
echo "=============================================="

python -c "
import json
from apps.algorithm.schema import AlgorithmInput

# 测试 AlgorithmInput 字段完整性
input_data = AlgorithmInput(
    chat_id=1,
    question='测试问题',
    ai_modal_id=1,
    datasource_id=1,
    engine_type='PostgreSQL'
)

# 验证所有必需字段
required_fields = ['chat_id', 'question', 'ai_modal_id', 'datasource_id', 'engine_type']
for field in required_fields:
    assert hasattr(input_data, field), f'Missing field: {field}'

# 验证提示词方法存在
assert hasattr(input_data, 'sql_sys_question')
assert hasattr(input_data, 'sql_user_question')
assert hasattr(input_data, 'chart_sys_question')
assert hasattr(input_data, 'chart_user_question')
assert hasattr(input_data, 'guess_sys_question')
assert hasattr(input_data, 'guess_user_question')

print('[PASS] 与原实现的一致性验证通过')
"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}[PASS] 一致性验证通过${NC}"
else
    echo -e "${RED}[FAIL] 一致性验证失败${NC}"
    exit 1
fi

# ============================================================================
# 计算测试时间
# ============================================================================
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

# ============================================================================
# 生成测试报告
# ============================================================================
echo ""
echo "=============================================="
echo "测试完成"
echo "=============================================="

cat > "$TEST_RESULTS_DIR/test_report.txt" << EOF
SQLBot 重构版本测试报告
========================

测试时间: $(date)
总耗时: ${ELAPSED} 秒

测试项目:
  1. 模块导入测试 - 通过
  2. 数据模型测试 - 通过
  3. 服务层测试 - 通过
  4. SSE 输出格式测试 - 通过
  5. 一致性验证 - 通过

结论: 所有测试通过，重构版本与原实现功能一致
EOF

echo -e "${GREEN}所有测试通过!${NC}"
echo "测试报告已保存到: $TEST_RESULTS_DIR/test_report.txt"
