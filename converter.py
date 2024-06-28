def read_file(file_name):
    with open(file_name, 'r') as file:
        lines = file.readlines()
    return [line.strip() for line in lines]

def save_file(file_name, data):
    with open(file_name, 'w') as file:
        for item in data:
            file.write(item + "\n")

def convert_addresses(addresses, format_type):
    converted = []
    for address in addresses:
        ip, port = address.split(':')
        if format_type == 'http':
            converted.append(f'http://{ip}:{port}')
        elif format_type == 'socks4':
            converted.append(f'socks4://{ip}:{port}')
        elif format_type == 'socks5':
            converted.append(f'socks5://{ip}:{port}')
    return converted

def main():
    input_file = input("Enter the input file name: ")
    addresses = read_file(input_file)
    
    print("Choose the format to save the addresses:")
    print("1. HTTP")
    print("2. SOCKS4")
    print("3. SOCKS5")
    
    format_choice = input("Enter the number of the chosen format: ")
    
    if format_choice == '1':
        format_type = 'http'
    elif format_choice == '2':
        format_type = 'socks4'
    elif format_choice == '3':
        format_type = 'socks5'
    else:
        print("Invalid choice")
        return
    
    converted_addresses = convert_addresses(addresses, format_type)
    
    output_file = input("Enter the output file name: ")
    save_file(output_file, converted_addresses)
    
    print(f"Addresses have been converted and saved to {output_file}")

if __name__ == "__main__":
    main()
