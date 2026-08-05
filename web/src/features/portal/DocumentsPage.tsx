import { useState } from 'react'
import type { FormEvent } from 'react'
import { useCreateDocument, useDocuments } from './api'

export function DocumentsPage() {
  const docs = useDocuments()
  const create = useCreateDocument()
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [openDoc, setOpenDoc] = useState<string | null>(null)

  const onCreate = (e: FormEvent) => {
    e.preventDefault()
    if (title.trim() === '' || body.trim() === '') return
    create.mutate({ title: title.trim(), category: 'other', body: body.trim() })
    setTitle('')
    setBody('')
  }

  return (
    <>
      <h1>Document vault</h1>
      <p className="hint">
        Text-only for the demo — real file storage is a Phase 9 concern. Never
        put PHI here (or anywhere in this system).
      </p>

      <section className="panel">
        <h2>Add document</h2>
        <form onSubmit={onCreate} className="row-form">
          <input
            placeholder="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <input
            placeholder="contents (text)"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <button type="submit" disabled={create.isPending}>
            Add
          </button>
        </form>
      </section>

      {docs.isPending && <p className="hint">loading…</p>}
      <table className="tbl">
        <thead>
          <tr>
            <th>Title</th>
            <th>Org</th>
            <th>Category</th>
            <th>Added</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {(docs.data ?? []).map((d) => (
            <tr key={d.id}>
              <td>{d.title}</td>
              <td>{d.org_name}</td>
              <td>
                <span className="badge b-issued">{d.category}</span>
              </td>
              <td>{new Date(d.created_at).toLocaleDateString()}</td>
              <td>
                <button
                  onClick={() => setOpenDoc(openDoc === d.id ? null : d.id)}
                >
                  {openDoc === d.id ? 'Hide' : 'View'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {openDoc !== null && (
        <section className="panel">
          <p>{docs.data?.find((d) => d.id === openDoc)?.body}</p>
        </section>
      )}
    </>
  )
}
