import SwiftUI

struct PopoverContentView: View {
    @ObservedObject var viewModel: UsageViewModel
    @State private var selectedTab = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HeaderSection(planType: viewModel.planType)
                .padding(.horizontal, 16)
                .padding(.top, 16)
                .padding(.bottom, 10)

            // Tab Picker
            Picker("", selection: $selectedTab) {
                Text("Session").tag(0)
                Text("Usage").tag(1)
                Text("Trends").tag(2)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.bottom, 12)

            // Tab Content
            ScrollView {
                Group {
                    switch selectedTab {
                    case 0:
                        SessionTabView(viewModel: viewModel)
                    case 1:
                        UsageTabView(viewModel: viewModel)
                    case 2:
                        TrendsTabView(viewModel: viewModel)
                    default:
                        EmptyView()
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 8)
            }

            // Footer
            VStack(spacing: 8) {
                Divider()

                HStack {
                    Text("Last updated: \(viewModel.lastUpdatedText)")
                        .font(.system(size: 11))
                        .foregroundStyle(.tertiary)
                    Spacer()
                    Button(action: { viewModel.load() }) {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 10))
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.borderless)
                }
                .padding(.horizontal, 16)

                Button(action: {
                    NSApplication.shared.terminate(nil)
                }) {
                    Text("Quit Claude Usage")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.borderless)
                .padding(.bottom, 12)
            }
        }
        .frame(width: 340, height: 560)
        .onAppear {
            viewModel.startWatching()
        }
        .onDisappear {
            viewModel.stopWatching()
        }
    }
}
