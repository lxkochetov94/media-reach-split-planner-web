from pathlib import Path
import sys

app = Path(sys.argv[1] if len(sys.argv) > 1 else 'budget-checker/src/app.js').read_text(encoding='utf-8')
css = Path(sys.argv[2] if len(sys.argv) > 2 else 'budget-checker/styles.css').read_text(encoding='utf-8')

required_app = [
    'Budget workspace UX v2',
    'Поиск по структуре',
    'Фильтры структуры',
    'budgetStructuralFilters',
    'budgetFilterOptions',
    'budgetMatchingLines',
    'budgetCollapsedPaths',
    'sessionStorage.setItem',
    'data-budget-collapse',
    'indeterminate',
    'Выгрузить весь бюджет',
    'Выгрузить выбранное',
    'Выгрузить отфильтрованное',
    'Выгрузить историю изменений',
    'budgetExportRows',
    'Итого до НДС, ₽',
    'База до НДС',
    'Актуально до НДС',
    'История ячейки',
    '<small>Было</small>',
    '<small>Изменение</small>',
    '<small>Стало</small>',
    'Комментарий <span class="required-mark">обязательно',
]
required_css = [
    'Budget workspace UX v2',
    '.budget-controlbar',
    '.budget-filter-panel',
    '.budget-hierarchy-toggle',
    '.budget-row-partial',
    '.budget-history-values',
]
for marker in required_app:
    if marker not in app:
        raise SystemExit(f'missing app marker: {marker}')
for marker in required_css:
    if marker not in css:
        raise SystemExit(f'missing css marker: {marker}')

current = app[app.index('function renderCurrent(){'):app.index('function renderHistory(){')]
if '<label>Поиск</label>' in current or '<label>Поиск по структуре</label>' in current:
    raise SystemExit('search label must not be rendered in the current-budget control bar')
if "scope=budgetNumbersForLines(matching,'current')" not in current:
    raise SystemExit('summary must be calculated from the filtered/search-matched lines')
if 'budgetSelectionStateForPath' not in current or 'budgetDescendantLines' not in current:
    raise SystemExit('hierarchical checkbox state is missing')
if 'budgetLineMatchesFilters(line,level)' not in current:
    raise SystemExit('dependent structural filters are missing')

for obsolete in ["['change','Внести изменение']", "['redistribute','Перераспределить бюджет']", "['flowchart','Сверить флоучарт']"]:
    if obsolete in app:
        raise SystemExit(f'obsolete standalone navigation remains: {obsolete}')

print('budget workspace UX v2 contract: OK')
