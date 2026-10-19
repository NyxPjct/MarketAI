import pytest
from app.batch_csv import CSVInputError, MAX_CSV_BYTES, preview_csv


def test_portuguese_excel_csv_preserves_gtin_and_decimal_comma():
    result = preview_csv('\ufeffProduto;Variante;Custo;Moeda;Quantidade;EAN\nPerfume;100 ml;"1.234,56";brl;2;0123456789012\n'.encode())
    row = result['rows'][0]
    assert row['valid']
    assert row['fields']['purchase_cost'] == 1234.56
    assert row['fields']['purchase_currency'] == 'BRL'
    assert row['fields']['quantity'] == 2
    assert row['fields']['gtin'] == '0123456789012'


def test_quoted_multiline_names_and_empty_rows():
    result = preview_csv(b'product_name,purchase_cost\n"A, product",12.50\n\n"multi\nline",10\n')
    assert result['valid_count'] == 2
    assert result['rows'][0]['fields']['product_name'] == 'A, product'
    assert result['rows'][1]['line'] == 5


def test_single_column_csv_uses_standard_analysis_defaults():
    result = preview_csv(b'product_name\nPhone\nPerfume\n')
    assert result['valid_count'] == 2
    assert result['rows'][0]['fields']['destination_country'] == 'BR'
    assert result['rows'][0]['fields']['desired_margin_percent'] == 20


@pytest.mark.parametrize('value', ['-1', 'NaN', 'Infinity', '1e9999', 'not-a-number'])
def test_invalid_cost_never_becomes_zero(value):
    result = preview_csv(f'product_name;purchase_cost\nPhone;{value}\n'.encode())
    assert result['invalid_count'] == 1


@pytest.mark.parametrize('columns,cells', [('quantity', '0'), ('quantity', '1.5'), ('destination_country', 'ZZ'),
    ('purchase_currency', 'INVALID'), ('marketplace_fee_percent;desired_margin_percent', '80;20')])
def test_invalid_quantities_countries_and_fees_are_blocked(columns, cells):
    assert preview_csv(f'product_name;{columns}\nPhone;{cells}\n'.encode())['invalid_count'] == 1


@pytest.mark.parametrize('content,code', [
    (b'product_name;produto\nA;B\n', 'duplicate_csv_columns'),
    (b'product_name;apikey\nA;B\n', 'unknown_csv_columns'),
    (b'purchase_cost\n10\n', 'product_name_column_required'),
    (b'product_name\n', 'csv_has_no_products'),
    (b'product_name\nP\xe9rfume\n', 'csv_requires_utf8'),
    (b'product_name\n"unterminated', 'invalid_csv'),
])
def test_invalid_files_have_explicit_errors(content, code):
    with pytest.raises(CSVInputError, match=code):
        preview_csv(content)


def test_limits_do_not_silently_truncate():
    assert preview_csv(('product_name\n' + 'Phone\n' * 50).encode())['valid_count'] == 50
    with pytest.raises(CSVInputError, match='csv_too_many_rows'):
        preview_csv(('product_name\n' + 'Phone\n' * 51).encode())
    with pytest.raises(CSVInputError, match='csv_too_large'):
        preview_csv(b'x' * (MAX_CSV_BYTES + 1))


def test_invalid_rows_do_not_block_other_rows():
    result = preview_csv(b'product_name;purchase_cost\nValid;10\nMissingCostCell\n;10\n')
    assert result['valid_count'] == 1 and result['invalid_count'] == 2
    assert result['rows'][1]['errors'][0]['code'] == 'column_count_mismatch'
