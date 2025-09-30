//
//  ViewController.swift
//  ImageView
//
//  Created by SeongWook Jang on 3/13/25.
//

import UIKit

class ViewController: UIViewController {
    var isZoom = false
    var imgOn: UIImage?
    var imgOff: UIImage?

    @IBOutlet var imgView: UIImageView!
    @IBOutlet var btnResize: UIButton!
    override func viewDidLoad() {
        super.viewDidLoad()
        // Do any additional setup after loading the view.
    }

    @IBAction func btnResizeImage(_ sender: UIButton) {
    }
    @IBAction func switchImageOnOff(_ sender: UISwitch) {
    }
    
}

