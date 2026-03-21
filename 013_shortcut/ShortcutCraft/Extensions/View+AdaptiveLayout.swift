import SwiftUI

extension View {
    @ViewBuilder
    func adaptiveSheet<Content: View>(
        isPresented: Binding<Bool>,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        #if os(iOS)
        self.sheet(isPresented: isPresented, content: content)
        #else
        self.sheet(isPresented: isPresented, content: content)
        #endif
    }
}

struct AdaptiveStack<Content: View>: View {
    let isHorizontal: Bool
    let spacing: CGFloat?
    @ViewBuilder let content: () -> Content

    var body: some View {
        if isHorizontal {
            HStack(spacing: spacing, content: content)
        } else {
            VStack(spacing: spacing, content: content)
        }
    }
}
