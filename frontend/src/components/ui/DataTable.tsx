import React, { useState, type ReactNode } from 'react';
import { Button } from './Button';

export interface ColumnDef<T> {
  key: string;
  header: string;
  sortable?: boolean;
  width?: string | number;
  render?: (row: T, index: number) => ReactNode;
  align?: 'left' | 'center' | 'right';
}

interface DataTableProps<T extends object> {
  columns: ColumnDef<T>[];
  data: T[];
  loading?: boolean;
  rowKey: (row: T) => string;
  pageSize?: number;
  totalCount?: number;
  currentPage?: number;
  onPageChange?: (page: number) => void;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
  selectedRows?: Set<string>;
  onRowSelect?: (key: string, selected: boolean) => void;
  onSelectAll?: (selected: boolean) => void;
}

type SortDir = 'asc' | 'desc';

const SKELETON_ROWS = 6;

function DataTableInner<T extends object>(
  props: DataTableProps<T>
): React.ReactElement {
  const {
    columns,
    data,
    loading = false,
    rowKey,
    pageSize = 20,
    totalCount,
    currentPage = 1,
    onPageChange,
    emptyMessage = 'No records found.',
    onRowClick,
    selectedRows,
    onRowSelect,
    onSelectAll,
  } = props;

  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const sortedData = React.useMemo(() => {
    if (!sortKey) return data;
    return [...data].sort((a, b) => {
      const aVal = (a as Record<string, unknown>)[sortKey];
      const bVal = (b as Record<string, unknown>)[sortKey];
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      const cmp = String(aVal).localeCompare(String(bVal), undefined, { numeric: true });
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [data, sortKey, sortDir]);

  const effectiveTotal = totalCount ?? data.length;
  const totalPages = Math.ceil(effectiveTotal / pageSize);
  const allSelected = selectedRows != null && data.length > 0 && data.every((r) => selectedRows.has(rowKey(r)));
  const someSelected = selectedRows != null && data.some((r) => selectedRows.has(rowKey(r)));

  const thStyle = (col: ColumnDef<T>): React.CSSProperties => ({
    padding: '10px 12px',
    textAlign: col.align ?? 'left',
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: '0.08em',
    color: 'var(--text-dim)',
    borderBottom: '1px solid var(--border)',
    whiteSpace: 'nowrap',
    cursor: col.sortable ? 'pointer' : 'default',
    userSelect: 'none',
    width: col.width,
    backgroundColor: 'var(--bg-surface)',
    position: 'sticky' as const,
    top: 0,
    zIndex: 1,
  });

  const tdStyle = (col: ColumnDef<T>): React.CSSProperties => ({
    padding: '9px 12px',
    textAlign: col.align ?? 'left',
    fontSize: 12,
    color: 'var(--text-primary)',
    borderBottom: '1px solid var(--border)',
    verticalAlign: 'middle',
  });

  const SortIcon: React.FC<{ colKey: string }> = ({ colKey }) => (
    <svg
      width="10"
      height="10"
      viewBox="0 0 24 24"
      fill="none"
      stroke={sortKey === colKey ? 'var(--accent)' : 'var(--text-dim)'}
      strokeWidth="2.5"
      strokeLinecap="round"
      style={{ display: 'inline', marginLeft: 4, verticalAlign: 'middle' }}
      aria-hidden="true"
    >
      {sortKey === colKey && sortDir === 'asc' ? (
        <path d="M12 19V5m-7 7l7-7 7 7" />
      ) : sortKey === colKey && sortDir === 'desc' ? (
        <path d="M12 5v14m-7-7l7 7 7-7" />
      ) : (
        <path d="M8 9l4-4 4 4M8 15l4 4 4-4" />
      )}
    </svg>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, overflowX: 'auto', overflowY: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: 12,
          }}
        >
          <thead>
            <tr>
              {(onRowSelect || onSelectAll) && (
                <th style={{ ...thStyle(columns[0]), width: 40 }}>
                  <input
                    type="checkbox"
                    checked={allSelected}
                    ref={(el) => { if (el) el.indeterminate = someSelected && !allSelected; }}
                    onChange={(e) => onSelectAll?.(e.target.checked)}
                    style={{ accentColor: 'var(--accent)', cursor: 'pointer' }}
                    aria-label="Select all rows"
                  />
                </th>
              )}
              {columns.map((col) => (
                <th
                  key={col.key}
                  style={thStyle(col)}
                  onClick={col.sortable ? () => handleSort(col.key) : undefined}
                >
                  {col.header}
                  {col.sortable && <SortIcon colKey={col.key} />}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: SKELETON_ROWS }).map((_, i) => (
                  <tr key={i}>
                    {(onRowSelect || onSelectAll) && <td style={tdStyle(columns[0])} />}
                    {columns.map((col) => (
                      <td key={col.key} style={tdStyle(col)}>
                        <div
                          className="skeleton"
                          style={{
                            height: 14,
                            width: `${60 + ((i * 13 + columns.indexOf(col) * 17) % 35)}%`,
                          }}
                        />
                      </td>
                    ))}
                  </tr>
                ))
              : sortedData.length === 0
              ? (
                <tr>
                  <td
                    colSpan={columns.length + (onRowSelect ? 1 : 0)}
                    style={{
                      padding: '40px 12px',
                      textAlign: 'center',
                      color: 'var(--text-dim)',
                      fontSize: 12,
                    }}
                  >
                    <svg
                      width="32"
                      height="32"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="var(--border-bright)"
                      strokeWidth="1.5"
                      style={{ display: 'block', margin: '0 auto 10px' }}
                      aria-hidden="true"
                    >
                      <circle cx="11" cy="11" r="8" />
                      <path d="M21 21l-4.35-4.35M11 8v6m0 2h.01" />
                    </svg>
                    {emptyMessage}
                  </td>
                </tr>
              )
              : sortedData.map((row, idx) => {
                  const key = rowKey(row);
                  const isSelected = selectedRows?.has(key) ?? false;
                  return (
                    <tr
                      key={key}
                      onClick={onRowClick ? () => onRowClick(row) : undefined}
                      style={{
                        backgroundColor: isSelected
                          ? 'var(--accent-dim)'
                          : idx % 2 === 0
                          ? 'transparent'
                          : 'rgba(255,255,255,0.015)',
                        cursor: onRowClick ? 'pointer' : 'default',
                        transition: 'background-color 100ms',
                      }}
                      onMouseEnter={(e) => {
                        if (!isSelected) (e.currentTarget as HTMLElement).style.backgroundColor = 'rgba(0,212,170,0.05)';
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLElement).style.backgroundColor = isSelected
                          ? 'var(--accent-dim)'
                          : idx % 2 === 0
                          ? 'transparent'
                          : 'rgba(255,255,255,0.015)';
                      }}
                    >
                      {onRowSelect && (
                        <td style={tdStyle(columns[0])} onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={(e) => onRowSelect(key, e.target.checked)}
                            style={{ accentColor: 'var(--accent)', cursor: 'pointer' }}
                            aria-label={`Select row ${key}`}
                          />
                        </td>
                      )}
                      {columns.map((col) => (
                        <td key={col.key} style={tdStyle(col)}>
                        {col.render
                            ? col.render(row, idx)
                            : String((row as Record<string, unknown>)[col.key] ?? '')}
                        </td>
                      ))}
                    </tr>
                  );
                })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && onPageChange && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 12px',
            borderTop: '1px solid var(--border)',
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
            Page {currentPage} of {totalPages} ({effectiveTotal} records)
          </span>
          <div style={{ display: 'flex', gap: 6 }}>
            <Button
              size="sm"
              variant="ghost"
              disabled={currentPage <= 1}
              onClick={() => onPageChange(currentPage - 1)}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
                <path d="M15 18l-6-6 6-6" />
              </svg>
              Prev
            </Button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const page = Math.max(1, Math.min(currentPage - 2, totalPages - 4)) + i;
              if (page > totalPages) return null;
              return (
                <Button
                  key={page}
                  size="sm"
                  variant={page === currentPage ? 'primary' : 'ghost'}
                  onClick={() => onPageChange(page)}
                >
                  {page}
                </Button>
              );
            })}
            <Button
              size="sm"
              variant="ghost"
              disabled={currentPage >= totalPages}
              onClick={() => onPageChange(currentPage + 1)}
            >
              Next
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export const DataTable = DataTableInner as <T extends object>(
  props: DataTableProps<T>
) => React.ReactElement;
