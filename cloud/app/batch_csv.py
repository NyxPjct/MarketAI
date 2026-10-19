"""CSV input validation shared by preview and execution; no market calls here."""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_BATCH_ROWS = 50
Amount = Annotated[float, Field(ge=0, le=1e12, allow_inf_nan=False)]
Percent = Annotated[float, Field(ge=0, lt=100, allow_inf_nan=False)]
Countries = Literal['BR', 'US', 'CN', 'FR', 'DE', 'GB', 'JP', 'KR', 'MX', 'AR', 'CA']
Currencies = Literal['BRL', 'USD', 'CNY', 'EUR', 'GBP', 'JPY', 'KRW', 'MXN', 'ARS', 'CAD']


class AnalysisFields(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    product_name: str = Field(min_length=1, max_length=240)
    sku: str = Field(default='', max_length=120)
    variant_text: str = Field(default='', max_length=240)
    purchase_cost: Amount = 0
    purchase_currency: Currencies = 'BRL'
    origin_country: Countries = 'CN'
    destination_country: Countries = 'BR'
    quantity: int = Field(default=1, ge=1, le=1_000_000)
    freight_total: Amount = 0
    import_cost_total: Amount = 0
    packaging_unit: Amount = 0
    other_costs_unit: Amount = 0
    marketplace_fee_percent: Percent = 16
    taxes_percent: Percent = 6
    ads_percent: Percent = 3
    desired_margin_percent: Percent = 20
    match_mode: Literal['strict', 'balanced'] = 'strict'
    gtin: str = Field(default='', max_length=32)
    ncm: str = Field(default='', max_length=32)
    supplier_name: str = Field(default='', max_length=240)
    national_reference_cost: Amount = 0

    @field_validator('purchase_currency', 'origin_country', 'destination_country', mode='before')
    @classmethod
    def uppercase_codes(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode='after')
    def valid_rates(self):
        if self.marketplace_fee_percent + self.taxes_percent + self.ads_percent + self.desired_margin_percent >= 100:
            raise ValueError('fees_and_margin_must_be_below_100')
        return self


class BatchRow(BaseModel):
    line: int = Field(ge=1)
    fields: AnalysisFields


class BatchCreate(BaseModel):
    client_id: UUID
    rows: list[BatchRow] = Field(min_length=1, max_length=MAX_BATCH_ROWS)


ALIASES = {
    'produto': 'product_name', 'nome': 'product_name', 'nome_do_produto': 'product_name',
    'variante': 'variant_text', 'custo': 'purchase_cost', 'custo_compra': 'purchase_cost',
    'moeda': 'purchase_currency', 'origem': 'origin_country', 'destino': 'destination_country',
    'pais_origem': 'origin_country', 'pais_destino': 'destination_country', 'quantidade': 'quantity',
    'frete_total': 'freight_total', 'importacao_total': 'import_cost_total',
    'embalagem_unidade': 'packaging_unit', 'outros_custos_unidade': 'other_costs_unit',
    'taxa_marketplace_percent': 'marketplace_fee_percent', 'impostos_percent': 'taxes_percent',
    'anuncios_percent': 'ads_percent', 'margem_desejada_percent': 'desired_margin_percent',
    'codigo': 'sku', 'codigo_produto': 'sku',
    'modo_match': 'match_mode', 'fornecedor': 'supplier_name', 'ean': 'gtin', 'upc': 'gtin',
}
NUMBER_FIELDS = {name for name in AnalysisFields.model_fields if name.endswith('_percent') or name in {
    'purchase_cost', 'quantity', 'freight_total', 'import_cost_total', 'packaging_unit',
    'other_costs_unit', 'national_reference_cost'}}


class CSVInputError(ValueError):
    pass


def normalized_header(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', value.strip().lower()) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '_', value).strip('_')


def decimal_value(value):
    """Accept decimal comma or point; prefer the rightmost separator when both exist."""
    value = value.strip().replace('\u00a0', '').replace(' ', '')
    if ',' in value and '.' in value:
        if value.rfind(',') > value.rfind('.'):
            value = value.replace('.', '').replace(',', '.')
        else:
            value = value.replace(',', '')
    else:
        value = value.replace(',', '.')
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError('invalid_number') from None
    if not result.is_finite():
        raise ValueError('invalid_number')
    return result


def preview_csv(content: bytes):
    if len(content) > MAX_CSV_BYTES:
        raise CSVInputError('csv_too_large')
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise CSVInputError('csv_requires_utf8') from None
    if not text.strip() or '\x00' in text:
        raise CSVInputError('invalid_csv')
    try:
        sample = text[:8192]
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=',;\t').delimiter
        except csv.Error:
            # A one-column product list has no delimiter; commas remain the default.
            delimiter = ';' if text.splitlines()[0].count(';') > text.splitlines()[0].count(',') else ','
        reader = csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True)
        headers = next(reader)
        names = [ALIASES.get(normalized_header(h), normalized_header(h)) for h in headers]
        if not names or len(set(names)) != len(names):
            raise CSVInputError('duplicate_csv_columns')
        unknown = set(names) - AnalysisFields.model_fields.keys()
        if unknown:
            raise CSVInputError('unknown_csv_columns')
        if 'product_name' not in names:
            raise CSVInputError('product_name_column_required')
        rows = []
        for cells in reader:
            if not any(cell.strip() for cell in cells):
                continue
            if len(rows) >= MAX_BATCH_ROWS:
                raise CSVInputError('csv_too_many_rows')
            row = {'line': reader.line_num, 'fields': {}, 'errors': []}
            if len(cells) != len(names):
                row['errors'].append({'field': 'row', 'code': 'column_count_mismatch'})
            values = {key: val.strip() for key, val in zip(names, cells) if val.strip()}
            row['fields'] = dict(values)
            for key in NUMBER_FIELDS & values.keys():
                try:
                    values[key] = decimal_value(values[key])
                except ValueError:
                    row['errors'].append({'field': key, 'code': 'invalid_number'})
            if not row['errors']:
                try:
                    row['fields'] = AnalysisFields.model_validate(values).model_dump()
                except ValidationError as exc:
                    row['errors'] = [{'field': str(e['loc'][-1]) if e['loc'] else 'rates',
                                      'code': e['type']} for e in exc.errors()]
            row['valid'] = not row['errors']
            rows.append(row)
        if not rows:
            raise CSVInputError('csv_has_no_products')
        return {'rows': rows, 'valid_count': sum(row['valid'] for row in rows),
                'invalid_count': sum(not row['valid'] for row in rows),
                'max_rows': MAX_BATCH_ROWS, 'delimiter': delimiter}
    except (csv.Error, StopIteration):
        raise CSVInputError('invalid_csv') from None
