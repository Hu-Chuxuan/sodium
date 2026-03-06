import fs from 'fs'

const COST_FILE_PATH = 'output/cost.json'

function getStoredTokens() {
  try {
    const raw = fs.readFileSync(COST_FILE_PATH, 'utf-8')
    const data = JSON.parse(raw)
    return [data.inputTokens ?? 0, data.outputTokens ?? 0]
  } catch {
    return [0,0]
  }
}

function saveTokens(input_tokens : any, output_tokens: any) {
  const json = JSON.stringify({ inputTokens: input_tokens, outputTokens: output_tokens }, null, 2)
  fs.writeFileSync(COST_FILE_PATH, json, 'utf-8')
}

export function addTokens(input_tokens: any, output_tokens: any) {
  const [currInput, currOutput] = getStoredTokens()
  saveTokens(currInput + input_tokens, currOutput + output_tokens)
}

export function getTotalTokens() {
  return getStoredTokens()
}

export function resetTokens() {
  saveTokens(0, 0)
}