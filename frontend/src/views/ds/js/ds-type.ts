import mysql_ds from '@/assets/datasource/icon_mysql.png'
import excel from '@/assets/datasource/icon_excel.png'
import oracle from '@/assets/datasource/icon_oracle.png'
import pg from '@/assets/datasource/icon_PostgreSQL.png'
import sqlServer from '@/assets/datasource/icon_SQL_Server.png'

export const dsType = [
  { label: 'MySQL', value: 'mysql' },
  { label: 'PostgreSQL', value: 'pg' },
  { label: 'Microsoft SQL Server', value: 'sqlServer' },
  { label: 'Oracle', value: 'oracle' },
  { label: 'Excel/CSV', value: 'excel' },
]

export const dsTypeWithImg = [
  { name: 'MySQL', type: 'mysql', img: mysql_ds },
  { name: 'PostgreSQL', type: 'pg', img: pg },
  { name: 'Microsoft SQL Server', type: 'sqlServer', img: sqlServer },
  { name: 'Oracle', type: 'oracle', img: oracle },
  { name: '本地 Excel/CSV', type: 'excel', img: excel },
]

export const haveSchema = ['sqlServer', 'pg', 'oracle']
