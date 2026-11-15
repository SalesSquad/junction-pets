import AppKit
import SwiftUI

final class WeakWindowReference {
    weak var value: NSWindow?
}

struct WindowReader: NSViewRepresentable {
    let onChange: (NSWindow?) -> Void
    func makeNSView(context: Context) -> WindowProbe { WindowProbe(onChange: onChange) }
    func updateNSView(_ nsView: WindowProbe, context: Context) { nsView.onChange = onChange }

    final class WindowProbe: NSView {
        var onChange: (NSWindow?) -> Void
        init(onChange: @escaping (NSWindow?) -> Void) { self.onChange = onChange; super.init(frame: .zero) }
        required init?(coder: NSCoder) { return nil }
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            let current = window
            DispatchQueue.main.async { [weak self] in self?.onChange(current) }
        }
    }
}
