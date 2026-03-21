import SwiftUI

struct BlockConfigView: View {
    let block: BlockInstance
    let definition: BlockDefinition
    let availableVariables: [VariableRef]
    let onUpdate: (String, ParameterValue) -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Header
                HStack(spacing: 12) {
                    Image(systemName: definition.iconName)
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(width: 40, height: 40)
                        .background(definition.categoryColor)
                        .clipShape(RoundedRectangle(cornerRadius: 10))

                    VStack(alignment: .leading, spacing: 2) {
                        Text(definition.name)
                            .font(.headline)
                        Text(definition.summary)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.bottom, 4)

                Divider()

                // Parameters
                if definition.parameters.isEmpty {
                    Text("설정할 매개변수가 없습니다")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.vertical, 20)
                } else {
                    ForEach(definition.parameters) { param in
                        ParameterEditorView(
                            parameter: param,
                            value: block.parameterValues[param.id] ?? param.defaultValue,
                            color: definition.categoryColor,
                            availableVariables: availableVariables
                        ) { newValue in
                            onUpdate(param.id, newValue)
                        }
                    }
                }

                // Info section
                VStack(alignment: .leading, spacing: 8) {
                    Divider()
                    Label {
                        Text("카테고리: \(definition.category.rawValue)")
                    } icon: {
                        Image(systemName: definition.category.iconName)
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)

                    if definition.inputType != .none {
                        Label {
                            Text("입력: \(definition.inputType.rawValue)")
                        } icon: {
                            Image(systemName: "arrow.right.circle")
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }

                    if definition.outputType != .none {
                        Label {
                            Text("출력: \(definition.outputType.rawValue)")
                        } icon: {
                            Image(systemName: "arrow.left.circle")
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }
                }
            }
            .padding()
        }
        .navigationTitle("블록 설정")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }
}

// MARK: - Parameter Editor

struct ParameterEditorView: View {
    let parameter: ParameterDefinition
    let value: ParameterValue?
    let color: Color
    let availableVariables: [VariableRef]
    let onUpdate: (ParameterValue) -> Void

    @State private var showVariablePicker = false
    @State private var inputMode: InputMode = .direct

    enum InputMode {
        case direct, variable
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(parameter.label)
                    .font(.system(size: 13, weight: .medium))
                if parameter.isRequired {
                    Text("*")
                        .foregroundStyle(.red)
                        .font(.caption)
                }
                Spacer()

                // Variable toggle (for text/number params)
                if parameter.type == .text || parameter.type == .number {
                    Menu {
                        Button {
                            inputMode = .direct
                        } label: {
                            Label("직접 입력", systemImage: "pencil")
                        }
                        Button {
                            showVariablePicker = true
                        } label: {
                            Label("변수 선택", systemImage: "tray.and.arrow.up")
                        }
                    } label: {
                        Image(systemName: inputMode == .variable ? "tray.and.arrow.up.fill" : "tray.and.arrow.up")
                            .font(.system(size: 12))
                            .foregroundStyle(inputMode == .variable ? color : .secondary)
                    }
                    .menuStyle(.borderlessButton)
                }
            }

            // Show variable pill if variable is selected
            if case .variable(let ref) = value {
                variablePill(ref: ref)
            } else {
                switch parameter.type {
                case .text:
                    textEditor
                case .number:
                    numberEditor
                case .boolean:
                    booleanEditor
                case .enumeration:
                    enumEditor
                case .stepper:
                    stepperEditor
                case .variable:
                    variableButton
                case .date:
                    textEditor
                }
            }
        }
        .sheet(isPresented: $showVariablePicker) {
            VariablePickerView(variables: availableVariables) { variable in
                inputMode = .variable
                onUpdate(.variable(variable))
            }
        }
    }

    private func variablePill(ref: VariableRef) -> some View {
        HStack(spacing: 6) {
            Circle()
                .fill(ref.color)
                .frame(width: 10, height: 10)
            Text(ref.displayName)
                .font(.system(size: 13, weight: .medium))
            Spacer()
            Button {
                inputMode = .direct
                onUpdate(.text(""))
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 14))
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(ref.color.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private var variableButton: some View {
        Button {
            showVariablePicker = true
        } label: {
            HStack {
                Image(systemName: "tray.and.arrow.up")
                Text("변수 선택")
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption)
            }
            .font(.system(size: 13))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(Color.secondary.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
    }

    private var textEditor: some View {
        TextField(
            parameter.placeholder ?? "",
            text: Binding(
                get: {
                    if case .text(let s) = value { return s }
                    return ""
                },
                set: { onUpdate(.text($0)) }
            )
        )
        .textFieldStyle(.roundedBorder)
    }

    private var numberEditor: some View {
        TextField(
            parameter.placeholder ?? "0",
            text: Binding(
                get: {
                    if case .number(let n) = value { return String(n) }
                    return ""
                },
                set: {
                    if let n = Double($0) {
                        onUpdate(.number(n))
                    }
                }
            )
        )
        .textFieldStyle(.roundedBorder)
        #if os(iOS)
        .keyboardType(.decimalPad)
        #endif
    }

    private var booleanEditor: some View {
        Toggle(isOn: Binding(
            get: {
                if case .boolean(let b) = value { return b }
                return false
            },
            set: { onUpdate(.boolean($0)) }
        )) {
            EmptyView()
        }
        .toggleStyle(.switch)
        .tint(color)
    }

    private var enumEditor: some View {
        Picker("", selection: Binding(
            get: {
                if case .enumValue(let s) = value { return s }
                return parameter.enumOptions?.first ?? ""
            },
            set: { onUpdate(.enumValue($0)) }
        )) {
            if let options = parameter.enumOptions {
                ForEach(options, id: \.self) { option in
                    Text(option).tag(option)
                }
            }
        }
        .pickerStyle(.menu)
    }

    private var stepperEditor: some View {
        HStack {
            Stepper(value: Binding(
                get: {
                    if case .number(let n) = value { return n }
                    return parameter.minValue ?? 0
                },
                set: { onUpdate(.number($0)) }
            ), in: (parameter.minValue ?? 0)...(parameter.maxValue ?? 100)) {
                if case .number(let n) = value {
                    Text("\(n, specifier: n.truncatingRemainder(dividingBy: 1) == 0 ? "%.0f" : "%.1f")")
                        .font(.system(size: 16, weight: .semibold, design: .rounded))
                        .foregroundStyle(color)
                }
            }
        }
    }
}
