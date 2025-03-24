import SwiftUI
import Foundation

// Pure JSON-based implementation with no hardcoded fallbacks
struct ChecklistView: View {
    let alertMessage: String
    @Environment(\.dismiss) private var dismiss
    @State private var isLoading = true
    @State private var title: String = ""
    @State private var steps: [(instruction: String, action: String, isConditional: Bool, indentLevel: Int)] = []
    @State private var errorMessage: String? = nil
    
    var body: some View {
        VStack {
            HStack {
                Text("Checklist")
                    .font(.headline)
                    .padding()
                Spacer()
                Button(action: {
                    dismiss()
                }) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.gray)
                        .font(.title2)
                }
                .padding()
            }
            
            if isLoading {
                ProgressView()
                    .padding()
            } else if !steps.isEmpty {
                VStack(alignment: .leading, spacing: 16) {
                    Text(title)
                        .font(.title)
                        .padding(.horizontal)
                    
                    Text(alertMessage)
                        .font(.title2)
                        .foregroundColor(.yellow)
                        .padding(.horizontal)
                    
                    Divider()
                    
                    ScrollView {
                        VStack(alignment: .leading, spacing: 12) {
                            ForEach(steps.indices, id: \.self) { index in
                                ChecklistStepView(step: steps[index])
                            }
                        }
                        .padding()
                    }
                }
            } else {
                VStack {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundColor(.yellow)
                        .padding()
                    
                    Text("No checklist available for this alert")
                        .font(.headline)
                    
                    Text("Alert: \(alertMessage)")
                        .font(.subheadline)
                        .foregroundColor(.gray)
                        .padding()
                    
                    if let errorMessage = errorMessage {
                        Text("Error: \(errorMessage)")
                            .font(.footnote)
                            .foregroundColor(.red)
                            .padding()
                    }
                }
                .padding()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .onAppear {
            // Load checklist data
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                loadChecklist()
            }
        }
    }
    
    // Structures to match SR22TG6-Checklists.json format
    struct ChecklistData: Codable {
        let id: String
        let title: String
        let section: String
        let subsection: String?
        let cas: String?
        let cas_type: String?
        let cas_description: String?
        let alert_message: String?
        let steps: [ChecklistStepData]
    }
    
    struct ChecklistStepData: Codable {
        let id: String
        let instruction: String
        let action: String
        let is_conditional: Bool
        let indent_level: Int
        let step_number: String
        let sub_steps: [ChecklistStepData]
    }
    
    private func loadChecklist() {
        // Debug logging
        print("Loading checklist for alert message: \(alertMessage)")
        
        // Load from JSON file
        if let url = Bundle.main.url(forResource: "SR22TG6-Checklists", withExtension: "json") {
            do {
                let data = try Data(contentsOf: url)
                let decoder = JSONDecoder()
                let checklists = try decoder.decode([ChecklistData].self, from: data)
                
                print("Successfully loaded \(checklists.count) checklists from JSON")
                
                // Find all checklists that match the alert message
                let matchingChecklists = checklists.filter { 
                    ($0.cas?.uppercased() == alertMessage.uppercased()) || 
                    ($0.alert_message?.uppercased() == alertMessage.uppercased())
                }
                
                print("Found \(matchingChecklists.count) matching checklists for \(alertMessage)")
                
                if let checklist = matchingChecklists.first {
                    print("Using checklist: \(checklist.title)")
                    title = checklist.title
                    
                    // Convert checklist steps to the format expected by the view
                    var convertedSteps: [(instruction: String, action: String, isConditional: Bool, indentLevel: Int)] = []
                    
                    // Function to recursively process steps and sub-steps
                    func processSteps(_ steps: [ChecklistStepData], parentIndentLevel: Int = 0) {
                        for step in steps {
                            convertedSteps.append((
                                instruction: step.instruction,
                                action: step.action,
                                isConditional: step.is_conditional,
                                indentLevel: step.indent_level + parentIndentLevel
                            ))
                            
                            // Process sub-steps recursively
                            if !step.sub_steps.isEmpty {
                                processSteps(step.sub_steps, parentIndentLevel: step.indent_level + 1)
                            }
                        }
                    }
                    
                    processSteps(checklist.steps)
                    steps = convertedSteps
                } else {
                    print("No matching checklist found for \(alertMessage)")
                    title = ""
                    steps = []
                    errorMessage = "No matching checklist found in SR22TG6-Checklists.json"
                    
                    // Debug: List all available CAS values
                    let allCasValues = checklists.compactMap { $0.cas }.sorted()
                    print("Available CAS values: \(allCasValues)")
                }
            } catch {
                print("Error loading checklist from JSON: \(error)")
                title = ""
                steps = []
                errorMessage = "Error loading checklist: \(error.localizedDescription)"
            }
        } else {
            print("SR22TG6-Checklists.json file not found in bundle")
            title = ""
            steps = []
            errorMessage = "SR22TG6-Checklists.json file not found in bundle"
        }
        
        isLoading = false
    }
}

struct ChecklistStepView: View {
    let step: (instruction: String, action: String, isConditional: Bool, indentLevel: Int)
    
    var body: some View {
        HStack(alignment: .top) {
            // Indentation based on level
            if step.indentLevel > 0 {
                ForEach(0..<step.indentLevel, id: \.self) { _ in
                    Rectangle()
                        .fill(Color.gray.opacity(0.3))
                        .frame(width: 2)
                        .padding(.horizontal, 8)
                }
            }
            
            VStack(alignment: .leading, spacing: 4) {
                if step.isConditional {
                    Text(step.instruction)
                        .font(.subheadline)
                        .foregroundColor(.blue)
                        .fontWeight(.medium)
                } else {
                    HStack(alignment: .top) {
                        Text(step.instruction)
                            .font(.body)
                        
                        Spacer()
                        
                        if !step.action.isEmpty {
                            Text(step.action)
                                .font(.body)
                                .fontWeight(.bold)
                                .foregroundColor(.primary)
                        }
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}
