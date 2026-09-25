import React, { Fragment, useMemo, useState } from 'react'

export default function DataTable({ columns, rows, rowKey = 'id', actions, selection = null, onRowClick = null, controlledSort = null, onSort = null, expandable = null }) {
  const [localSort, setLocalSort] = useState({ key: columns[0]?.key, dir: 'asc' })
  const serverControlled = Boolean(controlledSort && onSort)
  const sort = serverControlled ? controlledSort : localSort
  const sorted = useMemo(() => {
    if (serverControlled) return rows
    const copy = [...rows]
    if (!sort.key) return copy
    copy.sort((a, b) => {
      const av = valueFor(a, sort.key) ?? ''
      const bv = valueFor(b, sort.key) ?? ''
      return String(av).localeCompare(String(bv), 'hu', { numeric: true }) * (sort.dir === 'asc' ? 1 : -1)
    })
    return copy
  }, [rows, sort, serverControlled])

  function changeSort(column) {
    if (column.sortable === false) return
    if (serverControlled) {
      onSort(column.sortKey || column.key)
      return
    }
    const key = column.sortKey || column.key
    setLocalSort((current) => ({ key, dir: current.key === key && current.dir === 'asc' ? 'desc' : 'asc' }))
  }

  const selectedKeys = new Set(selection?.selectedKeys || [])
  const expandedKeys = new Set(expandable?.expandedKeys || [])
  const sortedKeys = sorted.map((row) => row[rowKey])
  const allSelected = Boolean(sortedKeys.length) && sortedKeys.every((key) => selectedKeys.has(key))
  const columnCount = columns.length + (selection ? 1 : 0) + (expandable ? 1 : 0) + (actions ? 1 : 0)

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {expandable && <th className="expander-column"><span className="sr-only">Kibontás</span></th>}
            {selection && (
              <th className="selection-column">
                <input
                  type="checkbox"
                  aria-label="Minden látható sor kijelölése"
                  checked={allSelected}
                  onChange={(event) => selection.onToggleAll(sortedKeys, event.target.checked)}
                />
              </th>
            )}
            {columns.map((col) => {
              const sortKey = col.sortKey || col.key
              const active = sort.key === sortKey
              return (
                <th
                  key={col.key}
                  onClick={() => changeSort(col)}
                  className={col.sortable === false ? '' : 'sortable'}
                  aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                >
                  {col.label}{active ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
                </th>
              )
            })}
            {actions && <th>Műveletek</th>}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const key = row[rowKey]
            const isExpanded = expandedKeys.has(key)
            return (
              <Fragment key={key}>
                <tr
                  className={`${selectedKeys.has(key) ? 'row-selected' : ''}${onRowClick ? ' clickable-row' : ''}${isExpanded ? ' row-expanded' : ''}`.trim()}
                  tabIndex={onRowClick ? 0 : undefined}
                  onClick={(event) => {
                    if (!onRowClick || event.target.closest('button, a, input, select, textarea, summary, details')) return
                    onRowClick(row)
                  }}
                  onKeyDown={(event) => {
                    if (!onRowClick || event.target.closest('button, a, input, select, textarea, summary, details')) return
                    if (event.key !== 'Enter' && event.key !== ' ') return
                    event.preventDefault()
                    onRowClick(row)
                  }}
                >
                  {expandable && (
                    <td className="expander-column">
                      <button
                        type="button"
                        className="row-expander-button"
                        aria-expanded={isExpanded}
                        aria-label={typeof expandable.label === 'function' ? expandable.label(row, isExpanded) : (isExpanded ? 'Részletek összecsukása' : 'Részletek kibontása')}
                        onClick={() => expandable.onToggle(row, !isExpanded)}
                      >
                        <span aria-hidden="true">{isExpanded ? '▾' : '▸'}</span>
                      </button>
                    </td>
                  )}
                  {selection && (
                    <td className="selection-column">
                      <input
                        type="checkbox"
                        aria-label={`Sor kijelölése: ${key}`}
                        checked={selectedKeys.has(key)}
                        onChange={(event) => selection.onToggle(key, event.target.checked)}
                      />
                    </td>
                  )}
                  {columns.map((col) => <td key={col.key}>{col.render ? col.render(row) : valueFor(row, col.key)}</td>)}
                  {actions && <td className="actions">{actions(row)}</td>}
                </tr>
                {expandable && isExpanded && (
                  <tr className="expanded-content-row">
                    <td colSpan={columnCount}>{expandable.render(row)}</td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function valueFor(row, key) {
  return key.split('.').reduce((acc, part) => acc?.[part], row)
}
