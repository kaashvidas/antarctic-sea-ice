/**
 * Opening splash screen: the product name at full size before the app's
 * own loading state takes over. Shown for a real minimum duration (not
 * just flashed for a frame if the backend responds instantly) so it
 * reads as an intentional opening beat, not a layout glitch.
 */
export default function Splash() {
  return (
    <div className="splash">
      <div className="splash-mark" aria-hidden="true">⬡</div>
      <h1 className="splash-title">KRYOS</h1>
      <p className="splash-subtitle">The Antarctic Voyage Navigator</p>
      <div className="splash-loader" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
    </div>
  )
}
