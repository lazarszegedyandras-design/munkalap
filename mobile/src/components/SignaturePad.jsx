import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'

const SignaturePad = forwardRef(function SignaturePad(_, ref) {
  const canvasRef = useRef(null)
  const drawing = useRef(false)
  const [hasInk, setHasInk] = useState(false)

  useEffect(() => {
    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const scale = Math.max(1, Math.min(window.devicePixelRatio || 1, 2))
    canvas.width = Math.round(rect.width * scale)
    canvas.height = Math.round(220 * scale)
    const ctx = canvas.getContext('2d')
    ctx.scale(scale, scale)
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, rect.width, 220)
    ctx.lineWidth = 2.2
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = '#111827'
  }, [])

  function point(event) {
    const rect = canvasRef.current.getBoundingClientRect()
    return { x: event.clientX - rect.left, y: event.clientY - rect.top }
  }
  function down(event) {
    event.preventDefault()
    drawing.current = true
    const p = point(event)
    const ctx = canvasRef.current.getContext('2d')
    ctx.beginPath(); ctx.moveTo(p.x, p.y)
    canvasRef.current.setPointerCapture?.(event.pointerId)
  }
  function move(event) {
    if (!drawing.current) return
    event.preventDefault()
    const p = point(event)
    const ctx = canvasRef.current.getContext('2d')
    ctx.lineTo(p.x, p.y); ctx.stroke()
    setHasInk(true)
  }
  function up(event) {
    drawing.current = false
    canvasRef.current.releasePointerCapture?.(event.pointerId)
  }
  function clear() {
    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const ctx = canvas.getContext('2d')
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.restore()
    setHasInk(false)
  }

  useImperativeHandle(ref, () => ({
    hasInk: () => hasInk,
    clear,
    toBlob: () => new Promise((resolve, reject) => canvasRef.current.toBlob(blob => blob ? resolve(blob) : reject(new Error('Az aláírás nem exportálható.')), 'image/png')),
  }), [hasInk])

  return <div className="signature-wrap">
    <canvas ref={canvasRef} className="signature-canvas" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} aria-label="Aláírási mező" />
    <button type="button" className="btn secondary small" onClick={clear}>Aláírás törlése</button>
  </div>
})

export default SignaturePad
