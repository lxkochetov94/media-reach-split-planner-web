from pathlib import Path
import sys

index=Path(sys.argv[1]).read_text(encoding='utf-8')
app=Path(sys.argv[2]).read_text(encoding='utf-8')
production=Path(sys.argv[3]).read_text(encoding='utf-8')

for marker in [
    '../mediaplan-checker/core.js',
    '../mediaplan-checker/production-rules.js',
]:
    if marker not in index:
        raise SystemExit(f'missing shared mediaplan script: {marker}')

for marker in [
    'LAB mediaplan checker reuse v1',
    'readMediaPlanWithChecker',
    'extractBudgetPlacements',
    'mpDetectBrand',
    'mpMatchChannel',
    'mpCompare',
    'CHANNEL_TOTAL_MISMATCH',
    'MISSING_AUX_COST',
    'UNMAPPED_CHANNEL',
    'Уточните бренд',
    'Сверка по каналам',
    'Что не сходится',
    'Ручное сопоставление',
]:
    if marker not in app:
        raise SystemExit(f'missing budget checker mediaplan marker: {marker}')

for marker in [
    'function extractBudgetPlacements',
    'core.extractBudgetPlacements=extractBudgetPlacements',
    "__labBudgetExtractorVersion='1'",
    'total cost after discount',
    'total cost \\+ adserving',
]:
    if marker not in production:
        raise SystemExit(f'missing reusable production parser marker: {marker}')

load=app[app.index('async function loadMediaPlan(file)'):app.index('function mediaPlanMappingHtml')]
if load.index('extractBudgetPlacements') > load.index('mpShowManual'):
    raise SystemExit('automatic parser must be attempted before manual mapping fallback')

print('budget mediaplan reuse contract: OK')
