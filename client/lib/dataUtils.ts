// Utility functions for cleaning and formatting proposal data

export interface Proposal {
  id?: number | string
  network?: string
  type?: string
  title?: string
  description?: string
  proposer?: string
  amount_numeric?: number
  currency?: string
  status?: string
  created_at?: string
  updated_at?: string
  [key: string]: any
}

// Clean text using regex to remove unwanted symbols and formatting
export function cleanText(text: string | null | undefined): string {
  if (!text) return '-'
  
  return String(text)
    // Remove markdown formatting
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/`(.*?)`/g, '$1')
    .replace(/#{1,6}\s*/g, '')
    // Remove extra whitespace and newlines
    .replace(/\s+/g, ' ')
    .replace(/\n+/g, ' ')
    // Remove special characters but keep basic punctuation
    .replace(/[^\w\s.,!?()-]/g, '')
    .trim()
}

// Get first line of description for table display
export function getFirstLine(text: string | null | undefined, maxLength: number = 100): string {
  if (!text) return '-'
  
  const cleaned = cleanText(text)
  const firstLine = cleaned.split('.')[0] // Get first sentence
  return firstLine.length > maxLength 
    ? firstLine.substring(0, maxLength) + '...'
    : firstLine
}

// Format amount with currency
export function formatAmount(amount: number | null | undefined, currency?: string): string {
  if (amount === null || amount === undefined) return '-'
  
  const formatted = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(amount)
  
  return currency ? `${formatted} ${currency}` : formatted
}

// Format date
export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '-'
  
  try {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    })
  } catch {
    return dateString
  }
}

// Format proposal type for display
export function formatProposalType(type: string | null | undefined): string {
  if (!type) return '-'
  
  return type
    .replace(/([A-Z])/g, ' $1') // Add space before capital letters
    .replace(/^./, str => str.toUpperCase()) // Capitalize first letter
    .trim()
}

// Extract proposal data from response content
export function extractProposalData(content: string): Proposal[] {
  try {
    // Look for JSON data in the content
    const jsonMatch = content.match(/\[{.*}\]/)
    if (jsonMatch) {
      const jsonData = JSON.parse(jsonMatch[0])
      if (Array.isArray(jsonData)) {
        return jsonData
      }
    }
    
    // Look for "Data: " prefix
    const dataMatch = content.match(/Data: (\[{.*}\])/)
    if (dataMatch) {
      const jsonData = JSON.parse(dataMatch[1])
      if (Array.isArray(jsonData)) {
        return jsonData
      }
    }
    
    // Try to parse the entire content as JSON
    const parsed = JSON.parse(content)
    if (Array.isArray(parsed)) {
      return parsed
    }
    
    return []
  } catch (e) {
    console.log('Failed to extract proposal data:', e)
    return []
  }
}

// Check if content contains proposal data
export function hasProposalData(content: string): boolean {
  return extractProposalData(content).length > 0
}
