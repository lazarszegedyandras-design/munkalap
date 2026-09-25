import React from 'react'

export default function ModulePlaceholder({ moduleName }) {
  return (
    <section>
      <div className="page-head"><h1>{moduleName}</h1></div>
      <div className="panel">
        <h2>A modul hozzáférési alapja elkészült</h2>
        <p>
          A modulválasztás, a frontend útvonalvédelem és a backend jogosultsági modell már aktív.
          A {moduleName} üzleti funkciói a következő fejlesztési fázisban kerülnek beépítésre.
        </p>
      </div>
    </section>
  )
}
